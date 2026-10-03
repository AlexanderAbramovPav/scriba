"""GigaAM v3 Russian ASR on Apple MPS, with Silero VAD and native word timing."""
from __future__ import annotations

from pathlib import Path
import tempfile


def normalize_segment(result, start, end):
    return {
        "start": start, "end": end, "text": result.text,
        "words": [{"word": w.text, "start": round(start + w.start, 3),
                   "end": round(start + w.end, 3)} for w in result.words or []],
    }


def transcribe(audio_path, model_name="v3_e2e_ctc", device="auto"):
    import gigaam
    import soundfile as sf
    import torch
    from faster_whisper.vad import get_speech_timestamps, VadOptions

    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else (
            "cuda" if torch.cuda.is_available() else "cpu")
    model = gigaam.load_model(model_name, device=device, use_flash=False,
                              fp16_encoder=device == "cuda")
    samples, sr = sf.read(audio_path, dtype="float32")
    if sr != 16000 or samples.ndim != 1:
        raise ValueError("GigaAM3 requires the pipeline's 16 kHz mono WAV")
    # The public GigaAM short-form API is limited to 25 s. Silero splits
    # speech at pauses before that limit, preserving absolute timestamps.
    spans = get_speech_timestamps(samples, VadOptions(
        max_speech_duration_s=20, min_silence_duration_ms=300, speech_pad_ms=200))
    segments = []
    with tempfile.TemporaryDirectory(prefix="scriba-gigaam3-") as tmp:
        clip = Path(tmp) / "chunk.wav"
        for span in spans:
            start, end = span["start"] / sr, span["end"] / sr
            sf.write(clip, samples[span["start"]:span["end"]], sr, subtype="PCM_16")
            result = model.transcribe(str(clip), word_timestamps=True)
            if result.text.strip():
                segments.append(normalize_segment(result, start, end))
            print(f"Transcript: [{start:.3f} --> {end:.3f}] {result.text}", flush=True)
    return {"segments": segments, "language": "ru"}
