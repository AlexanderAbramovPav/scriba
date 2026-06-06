#!/usr/bin/env python3
"""Optional GigaAM-RU ASR backend via sherpa-onnx (C5b).

Whisper large-v3 stays the default; GigaAM is opt-in for Russian (~-50% WER).
normalize_segments() maps sherpa-onnx recognition output to the whisperX shape so
C1 reconciliation + diarization word-assignment work unchanged.

Verified against sherpa-onnx 1.13.2 + GigaAM v3 transducer (2025-12-16):
  - the recognizer needs model_type="nemo_transducer" and an int8 encoder;
  - it emits CHARACTER-level `tokens` with per-char `timestamps` (+ `durations`),
    and uses a literal space token (" ") as the word separator.
So we group characters into words (chars_to_words) — otherwise downstream text
renders as "н е к у ю". If timestamps are absent, needs_alignment=True and the
caller aligns the text with whisperx.align (wav2vec) as a fallback.
"""
from __future__ import annotations
import os, sys


def _is_sep(tok: str) -> bool:
    """A word-separator token: a literal space (GigaAM) or a stripped-empty token."""
    return tok == " " or tok.strip() == ""


def chars_to_words(tokens, timestamps, durations=None):
    """Group character-level tokens into words on separator tokens.

    Each word's start = its first char's timestamp; end = last char's
    (timestamp + duration), falling back to the next char's timestamp or its own
    start. Returns a list of {word, start, end, score}. Pure function.
    """
    durations = durations or []
    words, cur, cur_start, cur_end = [], [], None, None
    for i, tok in enumerate(tokens):
        if _is_sep(tok):
            if cur:
                words.append({"word": "".join(cur), "start": round(cur_start, 3),
                              "end": round(cur_end, 3), "score": 1.0})
                cur, cur_start, cur_end = [], None, None
            continue
        start = float(timestamps[i])
        end = (start + float(durations[i])) if i < len(durations) else (
            float(timestamps[i + 1]) if i + 1 < len(timestamps) else start)
        if not cur:
            cur_start = start
        cur.append(tok)
        cur_end = max(cur_end if cur_end is not None else end, end)
    if cur:
        words.append({"word": "".join(cur), "start": round(cur_start, 3),
                      "end": round(cur_end, 3), "score": 1.0})
    return words


def normalize_segments(raw):
    """Map sherpa-onnx output to {segments:[{start,end,text,words[]}], needs_alignment}.

    Handles both character-level streams (GigaAM: separator tokens present → grouped
    into words) and word-level token lists (each token is a word)."""
    tokens = raw.get("tokens") or []
    ts = raw.get("timestamps") or []
    durs = raw.get("durations") or []
    text = (raw.get("text") or "").strip()
    if tokens and ts and len(tokens) == len(ts):
        if any(_is_sep(t) for t in tokens):
            words = chars_to_words(tokens, ts, durs)            # GigaAM char stream
        else:
            words = [{"word": tok, "start": round(float(ts[i]), 3),
                      "end": round(float(ts[i] + (durs[i] if i < len(durs) else 0)), 3),
                      "score": 1.0} for i, tok in enumerate(tokens)]  # word-level tokens
        if words:
            return {"segments": [{"start": words[0]["start"], "end": words[-1]["end"],
                                  "text": text, "words": words}], "needs_alignment": False}
    return {"segments": [{"start": 0.0, "end": 0.0, "text": text, "words": []}],
            "needs_alignment": True}


def model_dir():
    return os.environ.get("SCRIBA_GIGAAM_DIR", os.path.expanduser("~/.cache/scriba/gigaam"))


def _encoder_path(mdir):
    """GigaAM ships an int8 encoder; accept either name."""
    for name in ("encoder.onnx", "encoder.int8.onnx"):
        p = os.path.join(mdir, name)
        if os.path.exists(p):
            return p
    return os.path.join(mdir, "encoder.onnx")


def transcribe(audio_path, mdir=None):  # pragma: no cover - needs sherpa-onnx + model
    import sherpa_onnx, soundfile as sf
    mdir = mdir or model_dir()
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=_encoder_path(mdir), decoder=f"{mdir}/decoder.onnx",
        joiner=f"{mdir}/joiner.onnx", tokens=f"{mdir}/tokens.txt",
        num_threads=4, model_type="nemo_transducer")
    samples, sr = sf.read(audio_path, dtype="float32")
    if getattr(samples, "ndim", 1) > 1:
        samples = samples[:, 0]
    s = recognizer.create_stream()
    s.accept_waveform(sr, samples)
    recognizer.decode_stream(s)
    r = s.result
    return normalize_segments({"text": r.text, "tokens": list(getattr(r, "tokens", [])),
                               "timestamps": list(getattr(r, "timestamps", [])),
                               "durations": list(getattr(r, "durations", []))})


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) >= 3 and sys.argv[1] == "--probe":
        out = transcribe(sys.argv[2])
        seg = out["segments"][0]
        print(f"needs_alignment={out['needs_alignment']} words={len(seg['words'])} "
              f"text[:80]={seg['text'][:80]!r}")
