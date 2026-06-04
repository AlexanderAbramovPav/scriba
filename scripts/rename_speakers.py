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
    # Only rename bolded speaker labels: **Speaker N** -> **Name**
    def repl(m):
        label = m.group(1)
        return f"**{mapping.get(label, label)}**"
    return re.sub(r"\*\*(Speaker \d+)\*\*", repl, text)


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
    dest.write_text(apply_mapping(src.read_text(encoding="utf-8"), mapping), encoding="utf-8")
    print(f"Renamed {len(mapping)} speaker(s) -> {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
