#!/usr/bin/env python3
"""Meaningful output naming (C6d).

Folder/file are named from the source video (kebab). When the source name is
generic/uninformative, the agent supplies a --title; we kebab that. Pure string
logic. The CLI entry prints the resolved stem for transcribe.sh.
"""
from __future__ import annotations
import re, sys

_GENERIC = re.compile(
    r"^(zoom[_\-]?\d*|gmt[\d_\-]+|rec(ording)?\d*|video\d*|audio\d*|untitled\d*|"
    r"\d{4}-\d{2}-\d{2}([_\-]?\d+)?|new[_\-]?recording\d*)$", re.IGNORECASE)


def kebab(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def is_generic(name: str) -> bool:
    base = name.strip()
    if len(kebab(base)) < 4:
        return True
    return bool(_GENERIC.match(base))


def output_stem(input_stem: str, title: str | None = None) -> str:
    # A non-empty title wins; otherwise fall back to the input stem; if that kebabs to
    # "" (all-punctuation/whitespace name), default to "transcript" so the output never
    # lands in a hidden ".transcript/.md".
    stem = (kebab(title) if title else kebab(input_stem)) or "transcript"
    if len(stem) > 80:   # keep within the 255-byte filesystem name limit (multibyte-safe headroom)
        stem = stem[:80].rstrip("-") or "transcript"
    return stem


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "stem":
        title = sys.argv[3] if len(sys.argv) > 3 else None
        print(output_stem(sys.argv[2], title or None))
    elif cmd == "generic":
        print("1" if is_generic(sys.argv[2]) else "0")
