#!/usr/bin/env python3
"""Word-level diarization reconciliation (C1).

whisperX's assign_word_speakers labels each word, but a single ASR segment can
span a speaker change. Collapsing to one "dominant" speaker mis-attributes the
minority words. Here we (a) smooth lone 1-word speaker blips, then (b) split each
segment into single-speaker runs with word-accurate timings. Pure functions; no
ML deps so they unit-test instantly.
"""
from __future__ import annotations


def _timed_word(w):
    """True if the word carries a real speaker + start/end (not a punctuation/number token)."""
    return bool(w.get("speaker") and w.get("start") is not None and w.get("end") is not None)


def smooth_blips(words, min_blip_sec: float = 0.4):
    """Reassign an isolated single word whose duration < min_blip_sec when both
    neighbours share the *same other* speaker. Mutates copies, returns new list."""
    ws = [dict(w) for w in words]
    timed_idx = [i for i, w in enumerate(ws) if _timed_word(w)]
    for pos in range(1, len(timed_idx) - 1):
        i_prev, i_cur, i_next = timed_idx[pos - 1], timed_idx[pos], timed_idx[pos + 1]
        cur = ws[i_cur]
        prev_spk, next_spk = ws[i_prev]["speaker"], ws[i_next]["speaker"]
        dur = cur["end"] - cur["start"]
        if (cur["speaker"] != prev_spk and prev_spk == next_spk and dur < min_blip_sec):
            cur["speaker"] = prev_spk
    return ws


def split_segment_by_speaker(segment, min_blip_sec: float = 0.4):
    """Split one whisperX segment into consecutive single-speaker segments.

    Returns a list. If no word-level speakers exist (MLX path / diarization off),
    returns [segment] unchanged."""
    words = segment.get("words") or []
    if not any(_timed_word(w) for w in words):
        return [segment]

    smoothed = smooth_blips(words, min_blip_sec=min_blip_sec)
    out, cur = [], None
    for w in smoothed:
        spk = w.get("speaker")
        w_start = w.get("start")
        w_end = w.get("end")
        if spk is None or w_start is None:
            # attach stray token (punctuation) to the current run's text
            if cur is not None and w.get("word"):
                cur["_tokens"].append(w["word"])
            continue
        # whisperX assigns a speaker to unalignable tokens (e.g. numbers) that
        # carry start but NO end. Treat missing/None end as equal to start so the
        # emitted segment never carries a None end (downstream does `end - start`).
        if w_end is None:
            w_end = w_start
        if cur is None or spk != cur["speaker"]:
            if cur is not None:
                out.append(_finish(cur))
            cur = {"speaker": spk, "start": w_start, "end": w_end,
                   "_tokens": [w["word"]], "_words": [w]}
        else:
            cur["end"] = max(cur["end"], w_end)
            cur["_tokens"].append(w["word"])
            cur["_words"].append(w)
    if cur is not None:
        out.append(_finish(cur))
    return out or [segment]


def _finish(cur):
    text = "".join(t if t.startswith(" ") else " " + t for t in cur["_tokens"]).strip()
    return {"start": cur["start"], "end": cur["end"], "speaker": cur["speaker"],
            "text": text, "words": cur["_words"]}


def reconcile(result, min_blip_sec: float = 0.4):
    """Apply split_segment_by_speaker to every segment; preserve top-level keys."""
    new_segments = []
    for seg in result.get("segments", []):
        new_segments.extend(split_segment_by_speaker(seg, min_blip_sec=min_blip_sec))
    out = dict(result)
    out["segments"] = new_segments
    return out
