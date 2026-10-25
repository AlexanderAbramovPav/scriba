#!/usr/bin/env python3
"""Rename Speaker N labels to real names in a scriba Markdown file.

Usage:
  rename_speakers.py FILE.md "Alice,Bob"                 # positional -> Speaker 1, 2, ...
  rename_speakers.py FILE.md --map "Speaker 1=Alice,Speaker 2=Bob" [--out OUT.md]
"""
import argparse, pathlib, re, sys


def build_mapping(positional, explicit):
    mapping = {}
    if explicit:
        for pair in explicit.split(","):
            k, _, v = pair.partition("=")
            k, v = k.strip(), v.strip()
            if k and v:
                mapping[k] = v
    elif positional:
        for i, name in enumerate(positional.split(","), start=1):
            name = name.strip()
            if name:
                mapping[f"Speaker {i}"] = name
    return mapping


def apply_mapping(text, mapping):
    """Rename bolded speaker labels (**Speaker N** -> **Name**).

    Returns (new_text, renamed) where renamed counts real replacements per mapping key.
    """
    renamed = {}

    def repl(m):
        label = m.group(1)
        if label not in mapping:
            return m.group(0)
        renamed[label] = renamed.get(label, 0) + 1
        return f"**{mapping[label]}**"
    return re.sub(r"\*\*(Speaker \d+)\*\*", repl, text), renamed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("positional", nargs="?", default=None)
    ap.add_argument("--map", dest="explicit", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    mapping = build_mapping(a.positional, a.explicit)
    if not mapping:
        print("ERROR: no mapping provided", file=sys.stderr); sys.exit(2)

    src = pathlib.Path(a.file)
    dest = pathlib.Path(a.out) if a.out else src
    text, renamed = apply_mapping(src.read_text(encoding="utf-8"), mapping)
    unmatched = [k for k in mapping if k not in renamed]
    if unmatched:
        print(f"WARNING: no bold label in {src} for: {', '.join(unmatched)} "
              "(transcripts label speakers as `Speaker N`)", file=sys.stderr)
    if not renamed:
        print(f"ERROR: renamed 0 speakers; {src} left unchanged", file=sys.stderr); sys.exit(1)
    dest.write_text(text, encoding="utf-8")
    print(f"Renamed {len(renamed)} speaker(s), {sum(renamed.values())} label(s) -> {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
