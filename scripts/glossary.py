#!/usr/bin/env python3
"""Glossary resolution for ASR terminology biasing (C5a).

Project-scoped terms (`<dir>/.scriba/glossary.txt`) layer over global
(`~/.config/scriba/glossary`). One term per line; blank lines and '#' comments
ignored. Order preserved, project first, deduped case-sensitively.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path


def _read_terms(path: Path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            out.append(t)
    return out


def resolve_glossary(recording_dir):
    d = Path(recording_dir)
    project = _read_terms(d / ".scriba" / "glossary.txt")
    glob = _read_terms(Path(os.path.expanduser("~/.config/scriba/glossary")))
    seen, merged = set(), []
    for t in project + glob:
        if t not in seen:
            seen.add(t); merged.append(t)
    return merged


def build_prompt(terms):
    return ", ".join(terms)


if __name__ == "__main__":
    # usage: glossary.py --resolve <recording_dir>  -> prints the bias prompt (may be empty)
    if len(sys.argv) >= 3 and sys.argv[1] == "--resolve":
        print(build_prompt(resolve_glossary(sys.argv[2])))
