#!/usr/bin/env python3
"""Self-contained Diarization Error Rate (DER) — pure Python, zero third-party deps.

Why not pyannote.metrics / meeteval? Because scriba's whole pitch is "runs on a
normal Mac without a research stack". The benchmark should run anywhere plain
`python3` runs (and in CI), so the metric is implemented here from scratch.

Method (standard DER, interval-based, NO collar, overlap-aware):

  DER = (missed + false_alarm + confusion) / total_reference_speech

  - Parse RTTM turns `(start, end, speaker)` from ref and hyp.
  - Build a common timeline from EVERY boundary point in both annotations and
    walk consecutive micro-segments `[t_i, t_{i+1})`. Within a micro-segment the
    set of active ref speakers and active hyp speakers is constant.
  - For a micro-segment of duration `d`, under a candidate hyp→ref label mapping:
      ref_count = #distinct active ref speakers
      hyp_count = #distinct active (mapped) hyp speakers
      matched   = |mapped-hyp-speakers ∩ ref-speakers|
      missed       += d * max(0, ref_count - hyp_count)
      false_alarm  += d * max(0, hyp_count - ref_count)
      confusion    += d * (min(ref_count, hyp_count) - matched)
      total_ref    += d * ref_count
  - Speaker labels between hyp and ref are arbitrary, so we try ALL permutations
    mapping the (padded) hyp speaker set onto the ref speaker set and keep the one
    minimizing `missed + false_alarm + confusion`. Speaker counts are tiny (≤ ~6)
    so brute-force `itertools.permutations` is fine.

`der_from_turns(ref_turns, hyp_turns)` is the unit-friendly core;
`der(ref_rttm_path, hyp_rttm_path)` reads files. Returns a float in [0, ∞)
(0.0 for a perfect match; >1.0 is possible when false alarms exceed ref speech).
"""
from __future__ import annotations

import itertools
import sys

EPS = 1e-9


def parse_rttm(path):
    """Read an RTTM file → list of (start, end, speaker) turns.

    RTTM line layout (whitespace-separated):
        SPEAKER <file> <chan> <start> <dur> <NA> <NA> <speaker> <NA> <NA>
    Blank lines, comments (`#`/`;`) and non-SPEAKER lines are ignored.
    """
    turns = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line[0] in "#;":
                continue
            parts = line.split()
            if not parts or parts[0].upper() != "SPEAKER" or len(parts) < 8:
                continue
            try:
                start = float(parts[3])
                dur = float(parts[4])
            except ValueError:
                continue
            speaker = parts[7]
            if dur <= 0:
                continue
            turns.append((start, start + dur, speaker))
    return turns


def _boundaries(ref_turns, hyp_turns):
    pts = set()
    for s, e, _ in ref_turns:
        pts.add(s); pts.add(e)
    for s, e, _ in hyp_turns:
        pts.add(s); pts.add(e)
    return sorted(pts)


def _active(turns, t0, t1):
    """Distinct speakers active anywhere inside the half-open micro-segment."""
    mid = (t0 + t1) / 2.0
    return {spk for s, e, spk in turns if s <= mid < e}


def der_from_turns(ref_turns, hyp_turns):
    """Core DER over already-parsed turn lists. See module docstring for method."""
    bounds = _boundaries(ref_turns, hyp_turns)

    # Pre-compute, per micro-segment, the duration + active ref/hyp speaker sets.
    micro = []  # (duration, ref_active:set, hyp_active:set)
    total_ref = 0.0
    for t0, t1 in zip(bounds, bounds[1:]):
        d = t1 - t0
        if d <= EPS:
            continue
        ref_a = _active(ref_turns, t0, t1)
        hyp_a = _active(hyp_turns, t0, t1)
        micro.append((d, ref_a, hyp_a))
        total_ref += d * len(ref_a)

    if total_ref <= EPS:
        return 0.0

    ref_speakers = sorted({spk for _, _, spk in ref_turns})
    hyp_speakers = sorted({spk for _, _, spk in hyp_turns})

    # Pad the smaller label set with unique sentinels so the mapping is a bijection
    # over equal-sized sets; sentinels never appear in any micro-segment, so they
    # contribute nothing.
    n = max(len(ref_speakers), len(hyp_speakers), 1)
    ref_pad = ref_speakers + [f"__ref_pad_{i}__" for i in range(n - len(ref_speakers))]
    hyp_pad = hyp_speakers + [f"__hyp_pad_{i}__" for i in range(n - len(hyp_speakers))]

    best = None
    for perm in itertools.permutations(ref_pad):
        mapping = dict(zip(hyp_pad, perm))  # hyp label -> ref label
        missed = false_alarm = confusion = 0.0
        for d, ref_a, hyp_a in micro:
            mapped_hyp = {mapping[h] for h in hyp_a}
            rc = len(ref_a)
            hc = len(mapped_hyp)
            matched = len(mapped_hyp & ref_a)
            missed += d * max(0, rc - hc)
            false_alarm += d * max(0, hc - rc)
            confusion += d * (min(rc, hc) - matched)
        err = missed + false_alarm + confusion
        if best is None or err < best:
            best = err

    return best / total_ref


def der(ref_rttm_path, hyp_rttm_path):
    """Score a hypothesis RTTM against a reference RTTM. Returns DER as a float."""
    return der_from_turns(parse_rttm(ref_rttm_path), parse_rttm(hyp_rttm_path))


def turns_to_rttm(turns, file_id="hyp"):
    """Serialize (start, end, speaker) turns to RTTM text."""
    lines = []
    for s, e, spk in turns:
        lines.append(
            f"SPEAKER {file_id} 1 {s:.3f} {max(0.0, e - s):.3f} "
            f"<NA> <NA> {spk} <NA> <NA>"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def run(clip):  # pragma: no cover  (model-dependent end-to-end path)
    """Transcribe `clip` with scriba, derive a hyp RTTM from the sidecar's segment
    speakers, and score it against the sibling `<clip-stem>.rttm` reference.

    Requires the full pipeline (whisperX + pyannote). Documented + tested only by
    the pure-Python `der()` core above; this path is excluded from coverage.
    """
    import json
    import os
    import subprocess

    here = os.path.dirname(os.path.abspath(__file__))
    transcribe = os.path.join(here, "transcribe.sh")
    clip = os.path.abspath(clip)
    stem = os.path.splitext(os.path.basename(clip))[0]
    ref_rttm = os.path.join(os.path.dirname(clip), stem + ".rttm")
    if not os.path.exists(ref_rttm):
        sys.exit(f"ERROR: no reference RTTM next to clip: {ref_rttm}")

    # Run the pipeline; transcribe.sh prints the output <title>.md path on stdout.
    out = subprocess.run(
        ["bash", transcribe, clip],
        check=True, capture_output=True, text=True,
    ).stdout.strip().splitlines()
    md_path = out[-1] if out else ""
    rec_dir = os.path.dirname(md_path)  # <title>.transcript/
    sidecar = os.path.join(rec_dir, "data", "transcript.json")
    if not os.path.exists(sidecar):
        sys.exit(f"ERROR: no sidecar JSON produced: {sidecar}")

    with open(sidecar, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    hyp_turns = [
        (float(seg["start"]), float(seg["end"]), str(seg.get("speaker") or "UNK"))
        for seg in data.get("segments", [])
        if seg.get("start") is not None and seg.get("end") is not None
    ]

    # Persist the derived hypothesis RTTM next to the sidecar for inspection.
    hyp_rttm = os.path.join(rec_dir, "data", stem + ".hyp.rttm")
    with open(hyp_rttm, "w", encoding="utf-8") as fh:
        fh.write(turns_to_rttm(hyp_turns, file_id=stem))

    return der_from_turns(parse_rttm(ref_rttm), hyp_turns)


def main(argv):  # pragma: no cover
    usage = (
        "usage:\n"
        "  benchmark_der.py <clip.wav>            # transcribe + score vs sibling <clip>.rttm\n"
        "  benchmark_der.py <ref.rttm> <hyp.rttm> # score two RTTM files directly"
    )
    # Two-RTTM convenience mode (handy for demoing against benchmarks/sample.rttm).
    if len(argv) == 3 and argv[1].lower().endswith(".rttm") and argv[2].lower().endswith(".rttm"):
        print(f"DER = {der(argv[1], argv[2]) * 100:.2f}%")
        return
    if len(argv) != 2 or argv[1].lower().endswith(".rttm"):
        sys.exit(usage)
    value = run(argv[1])
    print(f"DER = {value * 100:.2f}%")


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv)
