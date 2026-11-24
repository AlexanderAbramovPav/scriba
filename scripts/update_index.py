#!/usr/bin/env python3
"""Corpus index for AI navigation (C6b).

Maintains `<recordings-dir>/.scriba/index.json` — one entry per recording so an
AI reads ONE file to find a meeting instead of scanning the folder. Writes are
atomic and serialized with an exclusive `fcntl.flock` lock on `index.lock` next
to the target `index.json` (on platforms without `fcntl`, updates fall back to
unlocked last-writer-wins behaviour). An existing index that cannot be read is
never overwritten (`IndexReadError`).

CLI:
  update_index.py upsert <scriba_dir> <entry_json>
  update_index.py record <scriba_dir> --id ID --title TITLE --date YYYY-MM-DD \\
      --duration SEC --folder FOLDER [--json TRANSCRIPT_JSON]
  update_index.py rebuild <recordings_dir> [--prune] [--dry-run]
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms without fcntl
    fcntl = None


class IndexReadError(Exception):
    """index.json exists but cannot be read as a scriba index; it is left untouched."""


def _load_index(idx_path):
    """Return the parsed index, or raise IndexReadError. Never guesses an empty index
    for an existing file: rewriting it would drop every recording it lists."""
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
    # ValueError covers JSONDecodeError and UnicodeDecodeError; RecursionError: deep nesting.
    except (OSError, ValueError, RecursionError) as e:
        raise IndexReadError(
            f"cannot read {idx_path}: {e}. The index was not updated. Restore the file "
            f"(from a backup, or fix the JSON), or move it away to start a new index."
        ) from e
    recs = data.get("recordings", []) if isinstance(data, dict) else None
    if not isinstance(recs, list) or not all(isinstance(r, dict) for r in recs):
        raise IndexReadError(
            f"{idx_path} is not a scriba index (expected an object with a "
            f'"recordings" list of objects). The index was not updated.'
        )
    return data


def _new_file_mode():
    # os.umask can only be read by setting it; 0o077 keeps the brief window restrictive.
    umask = os.umask(0o077)
    os.umask(umask)
    return 0o666 & ~umask


def _stat(path, follow):
    """os.stat / os.lstat that returns None only when the path does not exist. Any other
    error (EACCES, EIO, ESTALE, ELOOP …) must not be read as "no index yet"."""
    try:
        return os.stat(path) if follow else os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise IndexReadError(f"cannot access {path}: {e}. The index was not updated.") from e


def _fsync(fd):
    try:
        os.fsync(fd)
    except OSError as e:
        # Some FUSE / SMB / cloud-sync mounts do not implement fsync; the rename is
        # still atomic there, so do not fail the whole update for it.
        if e.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS):
            raise


@contextmanager
def _index_lock(lock_path, *, shared=False, create=True):
    """Hold an `fcntl.flock` lock on `lock_path` for the duration of the block.

    Takes an exclusive lock by default (`shared=True` uses `LOCK_SH`). When
    `create=False` (dry-run) and `lock_path` does not exist, yields without
    creating a file. Where `fcntl` does not exist, acts as a no-op (unlocked
    last-writer-wins behaviour).
    """
    if fcntl is None:
        yield
        return
    mode = "a+b" if create else "rb"
    try:
        f = open(lock_path, mode)
    except FileNotFoundError:
        if not create:
            yield
            return
        raise
    with f:
        op = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        fcntl.flock(f.fileno(), op)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _resolve_index_path(scriba_dir):
    """Resolve `<scriba_dir>/index.json`, following a valid symlink to its target.

    Returns `(idx_path, follow)` where `follow` is True if `index.json` was a
    symlink. A missing target file is fine (first run); a missing target
    directory raises `IndexReadError` (likely an unmounted volume).
    """
    idx_path = Path(scriba_dir) / "index.json"
    st = _stat(idx_path, follow=False)
    if st is not None and stat.S_ISLNK(st.st_mode):
        target = Path(os.path.realpath(idx_path))
        parent = _stat(target.parent, follow=True)
        if parent is None or not stat.S_ISDIR(parent.st_mode):
            raise IndexReadError(
                f"{idx_path} is a symlink to {os.readlink(idx_path)}, whose folder does not "
                f"exist (not mounted?). The index was not updated."
            )
        return target, True
    return idx_path, False


def _read_index_state(idx_path, follow):
    """Read `(data, file_mode)` for `idx_path`, refusing unreadable or non-regular files."""
    st = _stat(idx_path, follow=follow)
    if st is None:
        return {"schema_version": 1, "recordings": []}, _new_file_mode()
    if not stat.S_ISREG(st.st_mode):
        raise IndexReadError(f"{idx_path} is not a regular file. The index was not updated.")
    return _load_index(idx_path), stat.S_IMODE(st.st_mode)


def _write_index_atomic(idx_path, data, mode):
    """Write `data` to a temp file next to `idx_path`, fsync, preserve mode, and replace."""
    fd, tmp = tempfile.mkstemp(dir=str(idx_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            _fsync(f.fileno())
        try:
            os.chmod(tmp, mode)  # mkstemp creates 0600; keep the index's mode
        except OSError:
            pass  # some mounts reject chmod; a 0600 index beats no update
        os.replace(tmp, idx_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def build_entry(rec_id, title, date, duration, folder, transcript_json=None):
    """Assemble a corpus index entry from recording metadata and optional transcript JSON.

    Pulls `language` (default `"auto"`) and `low_confidence_pct` (default `0.0`)
    from `transcript_json` when readable; unreadable or missing JSON falls back
    to those defaults.
    """
    d = {}
    if transcript_json is not None:
        try:
            loaded = json.loads(Path(transcript_json).read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                d = loaded
        except Exception:
            d = {}
    lang = d.get("language")
    if lang is None:
        lang = "auto"
    raw_low = d.get("low_confidence_pct")
    low_conf_pct = float(0 if raw_low is None else raw_low)
    return {
        "id": rec_id,
        "title": title,
        "date": date,
        "lang": lang,
        "duration": int(duration),
        "folder": folder,
        "low_conf_pct": low_conf_pct,
    }


def upsert(scriba_dir, entry):
    """Insert or replace `entry` (keyed by `id`) in `<scriba_dir>/index.json`.

    Holds an exclusive `fcntl.flock` lock on `index.lock` next to the target
    `index.json` for the entire read-modify-write so concurrent updates never
    drop an entry. Where `fcntl` is unavailable, falls back to unlocked
    last-writer-wins behaviour.
    """
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
        raise ValueError("entry must be a JSON object with a non-empty string 'id'")
    scriba_dir = Path(scriba_dir)
    scriba_dir.mkdir(parents=True, exist_ok=True)
    idx_path, follow = _resolve_index_path(scriba_dir)
    with _index_lock(idx_path.parent / "index.lock"):
        data, mode = _read_index_state(idx_path, follow)
        recs = [r for r in data.get("recordings", []) if r.get("id") != entry["id"]]
        recs.append(entry)
        recs.sort(key=lambda r: str(r.get("date") or ""))
        data["recordings"] = recs
        _write_index_atomic(idx_path, data, mode)
    return idx_path


def _parse_yaml_scalar(raw):
    val = raw.strip()
    if not val:
        return ""
    if len(val) >= 2 and val[0] == '"' and '"' in val[1:]:
        end = 1
        while end < len(val):
            if val[end] == "\\" and end + 1 < len(val):
                end += 2
                continue
            if val[end] == '"':
                return val[1:end].replace('\\"', '"').replace("\\\\", "\\")
            end += 1
    if len(val) >= 2 and val[0] == "'" and "'" in val[1:]:
        end = 1
        while end < len(val):
            if val[end] == "'":
                if end + 1 < len(val) and val[end + 1] == "'":
                    end += 2
                    continue
                return val[1:end].replace("''", "'")
            end += 1
    for i, ch in enumerate(val):
        if ch == "#" and i > 0 and val[i - 1].isspace():
            val = val[:i].rstrip()
            break
    if val in ("null", "Null", "NULL", "~"):
        return ""
    return val


def _parse_front_matter(text):
    """Extract top-level key/value pairs from leading `---` YAML front matter.

    Returns a dict, or None if the text has no closed front matter block.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    closed = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped in ("---", "..."):
            closed = True
            break
        if not stripped or stripped.startswith("#") or line[0].isspace():
            continue
        key, sep, raw_val = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key:
            fm[key] = _parse_yaml_scalar(raw_val)
    return fm if closed else None


def _parse_duration(val):
    """Parse `hh:mm:ss` (or `mm:ss` / plain seconds) into integer seconds; 0 on invalid."""
    if not val:
        return 0
    s = str(val).strip()
    if not s:
        return 0
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = int(parts[0]), int(parts[1]), int(float(parts[2]))
            if h < 0 or m < 0 or sec < 0:
                return 0
            return h * 3600 + m * 60 + sec
        if len(parts) == 2:
            m, sec = int(parts[0]), int(float(parts[1]))
            if m < 0 or sec < 0:
                return 0
            return m * 60 + sec
        if len(parts) == 1:
            sec = int(float(parts[0]))
            return sec if sec >= 0 else 0
    except ValueError:
        return 0
    return 0


def _entry_from_markdown(md_path, rel_folder, stem):
    try:
        text = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm = _parse_front_matter(text)
    if fm is None:
        return None
    rec_id = fm.get("id") or stem
    date = fm.get("date") or ""
    duration = _parse_duration(fm.get("duration"))
    lang = fm.get("language") or "auto"
    raw_low = fm.get("low_confidence_pct")
    try:
        low_conf_pct = float(raw_low) if raw_low not in (None, "") else 0.0
    except ValueError:
        low_conf_pct = 0.0
    return {
        "id": rec_id,
        "title": stem,
        "date": date,
        "lang": lang,
        "duration": duration,
        "folder": rel_folder,
        "low_conf_pct": low_conf_pct,
    }


def _scan_transcripts(root):
    """Find every `*.transcript/<stem>.md` below `root` and parse its front matter."""
    entries = []
    skipped = []
    suffix = ".transcript"
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames.sort()
        keep = []
        for dname in dirnames:
            if dname == ".scriba":
                continue
            if dname.endswith(suffix) and len(dname) > len(suffix):
                rec_dir = Path(dirpath) / dname
                stem = dname[: -len(suffix)]
                md_path = rec_dir / f"{stem}.md"
                if md_path.is_file():
                    rel_folder = rec_dir.relative_to(root).as_posix()
                    entry = _entry_from_markdown(md_path, rel_folder, stem)
                    if entry is None:
                        skipped.append(md_path)
                    else:
                        entries.append(entry)
                continue
            keep.append(dname)
        dirnames[:] = keep
    return entries, skipped


def _apply_rebuild(root, idx_path, data, mode, scanned, skipped, *, prune, dry_run):
    existing_list = data.get("recordings", [])
    existing_by_id = {}
    for r in existing_list:
        rid = r.get("id")
        if isinstance(rid, str) and rid:
            existing_by_id[rid] = r

    scanned_by_id = {}
    for entry in scanned:
        scanned_by_id[entry["id"]] = entry

    added, updated, pruned, kept = [], [], [], []
    merged = []
    seen_existing_ids = set()

    for r in existing_list:
        rid = r.get("id")
        if isinstance(rid, str) and rid in scanned_by_id:
            continue
        if isinstance(rid, str) and rid:
            if rid in seen_existing_ids:
                continue
            seen_existing_ids.add(rid)
        folder = r.get("folder")
        folder_exists = (
            isinstance(folder, str)
            and bool(folder)
            and folder != "."
            and (root / folder).is_dir()
        )
        if prune and not folder_exists:
            pruned.append(r)
        else:
            kept.append(r)
            merged.append(r)

    for rid, entry in scanned_by_id.items():
        prev = existing_by_id.get(rid)
        if prev is None:
            added.append(entry)
        elif prev != entry:
            updated.append(entry)
        else:
            kept.append(entry)
        merged.append(entry)

    merged.sort(key=lambda r: str(r.get("date") or ""))
    if not dry_run:
        data["recordings"] = merged
        _write_index_atomic(idx_path, data, mode)

    return {
        "index_path": idx_path,
        "added": added,
        "updated": updated,
        "pruned": pruned,
        "kept": kept,
        "skipped": skipped,
        "total": len(merged),
        "dry_run": dry_run,
    }


def rebuild(recordings_dir, *, prune=False, dry_run=False):
    """Rebuild `<recordings_dir>/.scriba/index.json` from `*.transcript/<stem>.md` front matter.

    Existing entries whose folder is missing stay unless `prune=True`. When
    `dry_run=True`, computes changes and writes nothing (never creates `.scriba/`
    or `index.lock`). Uses the same exclusive `fcntl.flock` lock (unlocked where
    `fcntl` is unavailable) and unreadable-index refusal as `upsert`.
    """
    root = Path(recordings_dir)
    root_st = _stat(root, follow=True)
    if root_st is None or not stat.S_ISDIR(root_st.st_mode):
        raise FileNotFoundError(f"recordings directory not found: {root}")

    scanned, skipped = _scan_transcripts(root)
    scriba_dir = root / ".scriba"

    if dry_run:
        scriba_st = _stat(scriba_dir, follow=True)
        if scriba_st is None:
            idx_path = scriba_dir / "index.json"
            data = {"schema_version": 1, "recordings": []}
            return _apply_rebuild(
                root, idx_path, data, None, scanned, skipped, prune=prune, dry_run=True
            )
        if not stat.S_ISDIR(scriba_st.st_mode):
            raise IndexReadError(f"{scriba_dir} is not a directory. The index was not updated.")
        idx_path, follow = _resolve_index_path(scriba_dir)
        with _index_lock(idx_path.parent / "index.lock", shared=True, create=False):
            data, mode = _read_index_state(idx_path, follow)
            return _apply_rebuild(
                root, idx_path, data, mode, scanned, skipped, prune=prune, dry_run=True
            )

    scriba_dir.mkdir(parents=True, exist_ok=True)
    idx_path, follow = _resolve_index_path(scriba_dir)
    with _index_lock(idx_path.parent / "index.lock"):
        data, mode = _read_index_state(idx_path, follow)
        return _apply_rebuild(
            root, idx_path, data, mode, scanned, skipped, prune=prune, dry_run=False
        )


def find_index_dir(start):
    p = Path(start).resolve()
    for d in [p, *p.parents]:
        if (d / ".scriba").is_dir():
            return d / ".scriba"
    return None


def _build_parser():
    parser = argparse.ArgumentParser(prog="update_index.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_upsert = sub.add_parser("upsert", help="upsert a raw JSON entry into <scriba_dir>/index.json")
    p_upsert.add_argument("scriba_dir")
    p_upsert.add_argument("entry_json")

    p_record = sub.add_parser(
        "record", help="build an entry from metadata + optional transcript JSON and upsert it"
    )
    p_record.add_argument("scriba_dir")
    p_record.add_argument("--id", dest="rec_id", required=True)
    p_record.add_argument("--title", required=True)
    p_record.add_argument("--date", required=True)
    p_record.add_argument("--duration", required=True)
    p_record.add_argument("--folder", required=True)
    p_record.add_argument("--json", dest="transcript_json", default=None)

    p_rebuild = sub.add_parser(
        "rebuild", help="rebuild <recordings_dir>/.scriba/index.json from transcript front matter"
    )
    p_rebuild.add_argument("recordings_dir")
    p_rebuild.add_argument(
        "--prune", action="store_true", help="remove entries whose folder is gone"
    )
    p_rebuild.add_argument(
        "--dry-run", action="store_true", help="print what would change without writing"
    )
    return parser


def _print_rebuild_summary(res):
    for p in res["skipped"]:
        print(f"scriba: skipped {p} (missing or unreadable front matter)", file=sys.stderr)
    if res["dry_run"]:
        for entry in res["added"]:
            print(f"add    {entry['id']} ({entry.get('folder', '')})")
        for entry in res["updated"]:
            print(f"update {entry['id']} ({entry.get('folder', '')})")
        for entry in res["pruned"]:
            print(f"prune  {entry.get('id', '?')} ({entry.get('folder', '')})")
        if not (res["added"] or res["updated"] or res["pruned"]):
            print(f"Dry run: no changes (total {res['total']} recordings).")
        else:
            print(
                f"Dry run: would add {len(res['added'])}, update {len(res['updated'])}, "
                f"prune {len(res['pruned'])} (total {res['total']} recordings)."
            )
    else:
        print(
            f"Rebuilt {res['index_path']}: added {len(res['added'])}, "
            f"updated {len(res['updated'])}, pruned {len(res['pruned'])} "
            f"(total {res['total']} recordings)."
        )


def main(argv):
    parser = _build_parser()
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 2

    try:
        if args.cmd == "upsert":
            upsert(args.scriba_dir, json.loads(args.entry_json))
        elif args.cmd == "record":
            entry = build_entry(
                args.rec_id,
                args.title,
                args.date,
                args.duration,
                args.folder,
                args.transcript_json,
            )
            upsert(args.scriba_dir, entry)
        elif args.cmd == "rebuild":
            res = rebuild(args.recordings_dir, prune=args.prune, dry_run=args.dry_run)
            _print_rebuild_summary(res)
    except IndexReadError as e:
        print(f"scriba: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, RecursionError) as e:
        print(f"scriba: index not updated: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
