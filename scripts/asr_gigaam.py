#!/usr/bin/env python3
"""Optional GigaAM-RU ASR backend via sherpa-onnx (C5b).

Whisper large-v3 stays the default; GigaAM is opt-in for Russian (~-50% WER).
normalize_segments() maps sherpa-onnx recognition output to the whisperX shape so
C1 reconciliation + diarization word-assignment work unchanged. If the model does
not emit word/token timestamps, needs_alignment=True and the caller aligns the
text with whisperx.align (wav2vec) as a fallback.
"""
from __future__ import annotations
import os, sys


def normalize_segments(raw):
    tokens = raw.get("tokens") or []
    ts = raw.get("timestamps") or []
    durs = raw.get("durations") or []
    text = (raw.get("text") or "").strip()
    if tokens and ts and len(tokens) == len(ts):
        words = []
        for i, tok in enumerate(tokens):
            start = float(ts[i])
            end = start + float(durs[i]) if i < len(durs) else (
                float(ts[i + 1]) if i + 1 < len(ts) else start)
            words.append({"word": tok, "start": round(start, 3),
                          "end": round(end, 3), "score": 1.0})
        return {"segments": [{"start": words[0]["start"], "end": words[-1]["end"],
                              "text": text, "words": words}], "needs_alignment": False}
    return {"segments": [{"start": 0.0, "end": 0.0, "text": text, "words": []}],
            "needs_alignment": True}


def model_dir():
    return os.environ.get("SCRIBA_GIGAAM_DIR", os.path.expanduser("~/.cache/scriba/gigaam"))


def transcribe(audio_path, mdir=None):  # pragma: no cover - needs sherpa-onnx + model
    import sherpa_onnx, soundfile as sf
    mdir = mdir or model_dir()
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=f"{mdir}/encoder.onnx", decoder=f"{mdir}/decoder.onnx",
        joiner=f"{mdir}/joiner.onnx", tokens=f"{mdir}/tokens.txt", num_threads=4)
    samples, sr = sf.read(audio_path, dtype="float32")
    s = recognizer.create_stream(); s.accept_waveform(sr, samples)
    recognizer.decode_stream(s)
    r = s.result
    return normalize_segments({"text": r.text, "tokens": list(getattr(r, "tokens", [])),
                               "timestamps": list(getattr(r, "timestamps", [])),
                               "durations": list(getattr(r, "durations", []))})


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) >= 3 and sys.argv[1] == "--probe":
        out = transcribe(sys.argv[2])
        seg = out["segments"][0]
        print(f"needs_alignment={out['needs_alignment']} words={len(seg['words'])} text[:60]={seg['text'][:60]!r}")
