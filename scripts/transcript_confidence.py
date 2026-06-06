#!/usr/bin/env python3
"""Per-word confidence + overlap signals for the AI-facing sidecar (C2).

A transcript that is honest about its own uncertainty is higher-quality *as AI
input*. We expose three signals per word:
  - asr_conf      : whisperX/faster-whisper alignment score (passed through)
  - overlap       : word time intersects a region where >=2 speakers are active
  - speaker_conf  : margin of the assigned speaker over the next-best, in [0,1]
Pure functions over (segments, turns); turns = list of (start, end, label).
"""
from __future__ import annotations

LOW_ASR = 0.5          # below this asr_conf a word is "low confidence"
LOW_SPK = 0.5          # below this speaker_conf attribution is "shaky"


def overlap_regions(turns):
    """Intervals where >=2 speakers are simultaneously active. O(n log n) sweep."""
    events = []
    for s, e, _ in turns:
        events.append((s, 1)); events.append((e, -1))
    events.sort()
    regions, active, region_start = [], 0, None
    for t, delta in events:
        was = active
        active += delta
        if was < 2 <= active:
            region_start = t
        elif was >= 2 > active and region_start is not None:
            if t > region_start:
                regions.append((region_start, t))
            region_start = None
    return regions


def word_in_overlap(ws, we, regions):
    return bool(any(ws < re and we > rs for rs, re in regions))


def _intersect(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def speaker_confidence(ws, we, speaker, turns):
    """Fraction of the word covered by its assigned speaker minus the best competitor."""
    if we - ws <= 1e-6:   # zero-width word (e.g. an unalignable number token) — not assessable
        return 1.0
    dur = we - ws
    by_spk = {}
    for s, e, lbl in turns:
        ov = _intersect(ws, we, s, e)
        if ov > 0:
            by_spk[lbl] = by_spk.get(lbl, 0.0) + ov
    mine = by_spk.get(speaker, 0.0) / dur
    others = [v / dur for k, v in by_spk.items() if k != speaker]
    best_other = max(others) if others else 0.0
    return round(float(max(0.0, min(1.0, mine - best_other))), 3)


def enrich_segments(segments, turns):
    """Annotate each word with asr_conf/overlap/speaker_conf; flag each segment;
    return (segments, low_confidence_pct) where pct is the share of words flagged."""
    regions = overlap_regions(turns)
    # No diarization turns → single-speaker / diarization-off. Attribution is
    # "not applicable", not "shaky": confidence is full and it must not feed the
    # low-confidence predicate or the shaky_attribution flag.
    has_turns = bool(turns)
    total_words = flagged = 0
    for seg in segments:
        seg_overlap = seg_shaky = False
        for w in seg.get("words", []):
            if w.get("start") is None or w.get("end") is None:
                continue
            total_words += 1
            w["asr_conf"] = round(float(w.get("score", 1.0)), 3)
            w["overlap"] = word_in_overlap(w["start"], w["end"], regions)
            if has_turns:
                w["speaker_conf"] = speaker_confidence(
                    w["start"], w["end"], seg.get("speaker") or w.get("speaker"), turns)
                low = w["overlap"] or w["asr_conf"] < LOW_ASR or w["speaker_conf"] < LOW_SPK
                seg_shaky = seg_shaky or w["speaker_conf"] < LOW_SPK
            else:
                w["speaker_conf"] = 1.0
                low = w["overlap"] or w["asr_conf"] < LOW_ASR
            if low:
                flagged += 1
            seg_overlap = seg_overlap or w["overlap"]
        seg["flags"] = {"overlap": bool(seg_overlap), "shaky_attribution": bool(seg_shaky)}
    low_pct = round(100.0 * flagged / total_words, 1) if total_words else 0.0
    return segments, low_pct
