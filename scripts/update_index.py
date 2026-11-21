#!/usr/bin/env python3
"""Corpus index for AI navigation (C6b).

Maintains `<recordings-dir>/.scriba/index.json` — one entry per recording so an
AI reads ONE file to find a meeting instead of scanning the folder. Atomic write;
an existing index that cannot be read is never overwritten (IndexReadError).
CLI: update_index.py upsert <scriba_dir> <entry_json>
"""
from __future__ import annotations
import errno
import json
import os
import stat
import sys
import tempfile
from pathlib import Path


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


def upsert(scriba_dir, entry):
    # Last-writer-wins read-modify-write: assumes single-user / sequential runs. Two
    # transcriptions writing into the same .scriba/ at the same moment could read the
    # same base and the later os.replace() would drop the earlier one's entry.
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
        raise ValueError("entry must be a JSON object with a non-empty string 'id'")
    scriba_dir = Path(scriba_dir)
    scriba_dir.mkdir(parents=True, exist_ok=True)
    idx_path = scriba_dir / "index.json"
    st = _stat(idx_path, follow=False)
    if st is not None and stat.S_ISLNK(st.st_mode):
        # Update the real file and keep the link. A missing target file is fine (first
        # run), a missing target directory is not: it is most likely an unmounted volume.
        target = Path(os.path.realpath(idx_path))
        parent = _stat(target.parent, follow=True)
        if parent is None or not stat.S_ISDIR(parent.st_mode):
            raise IndexReadError(
                f"{idx_path} is a symlink to {os.readlink(idx_path)}, whose folder does not "
                f"exist (not mounted?). The index was not updated."
            )
        idx_path = target
        st = _stat(idx_path, follow=True)
    if st is None:
        data = {"schema_version": 1, "recordings": []}
        mode = _new_file_mode()
    elif not stat.S_ISREG(st.st_mode):
        raise IndexReadError(f"{idx_path} is not a regular file. The index was not updated.")
    else:
        data = _load_index(idx_path)
        mode = stat.S_IMODE(st.st_mode)
    recs = [r for r in data.get("recordings", []) if r.get("id") != entry["id"]]
    recs.append(entry)
    recs.sort(key=lambda r: str(r.get("date") or ""))
    data["recordings"] = recs
    # Atomic: write a temp file in the same directory, then rename over the index.
    fd, tmp = tempfile.mkstemp(dir=str(idx_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            _fsync(f.fileno())
        os.chmod(tmp, mode)  # mkstemp creates 0600; keep the index's mode
        os.replace(tmp, idx_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return idx_path


def find_index_dir(start):
    p = Path(start).resolve()
    for d in [p, *p.parents]:
        if (d / ".scriba").is_dir():
            return d / ".scriba"
    return None


def main(argv):
    if len(argv) != 4 or argv[1] != "upsert":
        print("usage: update_index.py upsert <scriba_dir> <entry_json>", file=sys.stderr)
        return 2
    try:
        upsert(argv[2], json.loads(argv[3]))
    except IndexReadError as e:
        print(f"scriba: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, RecursionError) as e:
        print(f"scriba: index not updated: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
