#!/usr/bin/env python3
"""Corpus index for AI navigation (C6b).

Maintains `<recordings-dir>/.scriba/index.json` — one entry per recording so an
AI reads ONE file to find a meeting instead of scanning the folder. Atomic write;
an existing index that cannot be read is never overwritten (IndexReadError).
CLI: update_index.py upsert <scriba_dir> <entry_json>
"""
from __future__ import annotations
import json
import os
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
    except (OSError, ValueError) as e:  # ValueError covers JSONDecodeError and UnicodeDecodeError
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


def upsert(scriba_dir, entry):
    # Last-writer-wins read-modify-write: assumes single-user / sequential runs. Two
    # transcriptions writing into the same .scriba/ at the same moment could read the
    # same base and the later os.replace() would drop the earlier one's entry.
    scriba_dir = Path(scriba_dir)
    scriba_dir.mkdir(parents=True, exist_ok=True)
    idx_path = scriba_dir / "index.json"
    if idx_path.exists():
        data = _load_index(idx_path)
    else:
        data = {"schema_version": 1, "recordings": []}
    recs = [r for r in data.get("recordings", []) if r.get("id") != entry["id"]]
    recs.append(entry)
    recs.sort(key=lambda r: r.get("date", ""))
    data["recordings"] = recs
    # Atomic: write a temp file in the same directory, then rename over the index.
    fd, tmp = tempfile.mkstemp(dir=str(scriba_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
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


if __name__ == "__main__":
    if sys.argv[1] == "upsert":
        try:
            upsert(sys.argv[2], json.loads(sys.argv[3]))
        except IndexReadError as e:
            print(f"scriba: {e}", file=sys.stderr)
            sys.exit(1)
