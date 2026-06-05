#!/usr/bin/env python3
"""Corpus index for AI navigation (C6b).

Maintains `<recordings-dir>/.scriba/index.json` — one entry per recording so an
AI reads ONE file to find a meeting instead of scanning the folder. Atomic write.
CLI: update_index.py upsert <scriba_dir> <entry_json>
"""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path


def upsert(scriba_dir, entry):
    # Last-writer-wins read-modify-write: assumes single-user / sequential runs. Two
    # transcriptions writing into the same .scriba/ at the same moment could read the
    # same base and the later os.replace() would drop the earlier one's entry.
    scriba_dir = Path(scriba_dir); scriba_dir.mkdir(parents=True, exist_ok=True)
    idx_path = scriba_dir / "index.json"
    data = {"schema_version": 1, "recordings": []}
    if idx_path.exists():
        try:
            data = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    recs = [r for r in data.get("recordings", []) if r.get("id") != entry["id"]]
    recs.append(entry)
    recs.sort(key=lambda r: r.get("date", ""))
    data["recordings"] = recs
    fd, tmp = tempfile.mkstemp(dir=str(scriba_dir), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, idx_path)
    return idx_path


def find_index_dir(start):
    p = Path(start).resolve()
    for d in [p, *p.parents]:
        if (d / ".scriba").is_dir():
            return d / ".scriba"
    return None


if __name__ == "__main__":
    if sys.argv[1] == "upsert":
        upsert(sys.argv[2], json.loads(sys.argv[3]))
