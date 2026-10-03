#!/usr/bin/env python3
"""Export text for the host AI; apply only verified punctuation/case edits.

No model or API calls: the agent driving Scriba supplies the edited JSON.
The source sidecar is immutable; word times/scores remain the ASR evidence.
"""
import argparse
import copy
import hashlib
import json
import pathlib
import re
import unicodedata


def normalized(text):
    return unicodedata.normalize("NFC", text).casefold()


def signature(text):
    text = normalized(text)
    tokens = re.findall(r"\w+(?:[-'’]\w+)*|[^\w\s]", text)
    words = [t for t in tokens if re.match(r"\w", t) or
             unicodedata.category(t)[0] in "SM" or t in "/\\%#@"]
    numbers = re.findall(r"(?<!\w)[+−-]?\d+(?:[.,:/-]\d+)*", text)
    return words, numbers


def validate_edit(before, after):
    if not isinstance(after, str) or signature(before) != signature(after):
        raise ValueError("Edit changes words, their order, numbers, or meaningful symbols")
    if any(not (c.isalnum() or c.isspace() or unicodedata.category(c)[0] in "PSM")
           for c in after):
        raise ValueError("Unsupported character in edited text")


def read_source(path):
    raw = pathlib.Path(path).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise ValueError("Expected a Scriba sidecar with segments")
    if data.get("postprocessing", {}).get("punctuation"):
        raise ValueError("Export from the raw ASR sidecar, not an already punctuated copy")
    return data, hashlib.sha256(raw).hexdigest()


def export(path):
    data, digest = read_source(path)
    return {"source_sha256": digest, "segments": [
        {"id": i, "speaker": s.get("speaker"), "start": s["start"],
         "end": s["end"], "text": s["text"]}
        for i, s in enumerate(data["segments"])]}


def apply(path, edits):
    data, digest = read_source(path)
    if edits.get("source_sha256") != digest:
        raise ValueError("Source changed: export again before applying edits")
    rows = edits.get("segments")
    if not isinstance(rows, list) or len(rows) != len(data["segments"]):
        raise ValueError("Edits must cover every source segment exactly once")
    seen = set()
    result = copy.deepcopy(data)
    for row in rows:
        if set(row) != {"id", "text"}:
            raise ValueError("Each edit may contain only id and text")
        idx = row["id"]
        if type(idx) is not int or idx in seen or not 0 <= idx < len(rows):
            raise ValueError("Duplicate or invalid segment id")
        seen.add(idx)
        original = data["segments"][idx]["text"]
        validate_edit(original, row["text"])
        result["segments"][idx]["raw_text"] = original
        result["segments"][idx]["text"] = row["text"]
    result.setdefault("postprocessing", {})["punctuation"] = {
        "method": "host-ai", "validation": "words-numbers-symbols-preserved",
        "source_sha256": digest, "word_text": "raw-asr"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("input")
    ex.add_argument("--output", required=True)
    ap = sub.add_parser("apply")
    ap.add_argument("input")
    ap.add_argument("edits")
    ap.add_argument("--output", required=True)
    args = parser.parse_args()
    output = pathlib.Path(args.output)
    inputs = [pathlib.Path(args.input)]
    if args.command == "apply":
        inputs.append(pathlib.Path(args.edits))
    if any(output.resolve() == p.resolve() for p in inputs):
        parser.error("Output must be separate from the raw source and edits")
    try:
        result = export(args.input) if args.command == "export" else apply(
            args.input, json.loads(pathlib.Path(args.edits).read_text(encoding="utf-8")))
    except (ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Punctuation rejected: {exc}\n")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
