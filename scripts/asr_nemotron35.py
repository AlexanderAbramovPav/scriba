"""Opt-in NVIDIA Nemotron 3.5 Transcribe (speech-LLM) via NeMo-Speech.cpp.

One native pass gives punctuated text, CTC word times and, with --diarize,
speaker tags. Speech-LLM (SALM) support exists only in NeMo-Speech.cpp nightly
builds (66d50d9 or newer); the 0.2.0 release used for Nemotron 3 lacks it.
See references/local-backends.md.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

MAX_AUDIO_SEC = 3600  # one request holds at most one hour of audio
DEFAULT_MODEL = "~/.cache/scriba/nemotron35/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-AD-IQ4_NL.gguf"
# The instruction measured on the T104 EN/DE fixtures (0% WER). Override with
# SCRIBA_NEMOTRON35_INSTRUCTION to test variants; {language} is the language name.
INSTRUCTION = ("Transcribe this {language}audio with punctuation and capitalization. "
               "Include all spoken words and verbal fillers. Write numbers in their standard "
               "written form. Put speaker tags <spk:0> <spk:1> <spk:2> <spk:3> on the transcription.")
LANGUAGE_NAMES = {
    "en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "cs": "Czech", "sk": "Slovak",
    "ru": "Russian", "uk": "Ukrainian", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "hi": "Hindi", "tr": "Turkish", "sv": "Swedish", "da": "Danish", "fi": "Finnish",
}
SENTENCE_END = (".", "?", "!", "…")


def executable() -> str | None:
    for var in ("SCRIBA_NEMOTRON35_BIN", "SCRIBA_NEMO_BIN"):
        explicit = os.environ.get(var)
        if explicit:
            if not (Path(explicit).is_file() and os.access(explicit, os.X_OK)):
                raise FileNotFoundError(f"{var} is not executable: {explicit}")
            return explicit
    return shutil.which("nemo-speech")


def supports_salm(help_text: str) -> bool:
    """A SALM-capable build documents --instruction for `transcribe`."""
    return "--instruction" in help_text


def model_path(model: str | None = None) -> Path:
    raw = model or os.environ.get("SCRIBA_NEMOTRON35_MODEL") or DEFAULT_MODEL
    return Path(os.path.expanduser(raw))


def embedded_speakers(diarizer="auto", num_speakers=None, enroll=None) -> bool:
    """Use the model's own speaker tags unless pyannote is requested or its controls are."""
    return diarizer != "pyannote" and num_speakers is None and not enroll


def check_duration(audio_sec: float) -> None:
    if audio_sec > MAX_AUDIO_SEC:
        raise ValueError(f"Nemotron 3.5 Transcribe accepts at most {MAX_AUDIO_SEC // 60} minutes "
                         f"per request ({audio_sec / 60:.1f} min given); split the file or use the default backend")


def instruction(language: str | None, glossary: str | None = None) -> str:
    template = os.environ.get("SCRIBA_NEMOTRON35_INSTRUCTION") or INSTRUCTION
    name = LANGUAGE_NAMES.get(language or "", "")
    text = template.replace("{language}", f"{name} " if name else "")
    if glossary:
        text += f" Possible terms: {glossary}."
    return text


def build_command(binary, audio_path, model, output, *, language=None, glossary=None,
                  diarize=True, device="metal"):
    command = [binary, "transcribe", str(audio_path), "--model", str(model),
               "--format", "json", "--word-times", "--device", device,
               "-o", str(output), "--force",
               # Memory settings measured on a 36 GB Mac: one request, no speculative draft.
               "--asr.salm.max_sequences", "1", "--asr.salm.mtp_draft", "0",
               "--instruction", instruction(language, glossary)]
    if language:
        command += ["-l", language]
    if diarize:
        command.append("--diarize")
    return command


def _speaker(raw):
    # Native tags are ints; 0 is falsy, so labels become strings at this boundary.
    return None if raw is None else f"speaker_{raw}"


def to_segments(data, max_gap=1.0):
    """Split native flat words into segments at speaker changes, pauses and sentence ends."""
    segments, current = [], []
    for raw in data.get("words") or []:
        start, end = float(raw["start"]), float(raw["end"])
        if not (math.isfinite(start) and math.isfinite(end)) or start < 0 or end < start:
            raise ValueError("Invalid Nemotron 3.5 word timing")
        # The native JSON reports confidence 0 as a placeholder, not a score.
        word = {"word": raw["word"], "start": round(start, 3), "end": round(end, 3)}
        speaker = _speaker(raw.get("speaker"))
        if speaker is not None:
            word["speaker"] = speaker
        if current and (word.get("speaker") != current[-1].get("speaker")
                        or start - current[-1]["end"] > max_gap
                        or current[-1]["word"].endswith(SENTENCE_END)):
            segments.append(current)
            current = []
        current.append(word)
    if current:
        segments.append(current)
    out = []
    for words in segments:
        seg = {"start": words[0]["start"], "end": words[-1]["end"],
               "text": " ".join(w["word"] for w in words), "words": words}
        if "speaker" in words[0]:
            seg["speaker"] = words[0]["speaker"]
        out.append(seg)
    return out


def speaker_turns(segments):
    """Contiguous speaker runs, used as the overlap-free turn list."""
    turns = []
    for seg in segments:
        spk = seg.get("speaker")
        if spk is None:
            continue
        if turns and turns[-1][2] == spk:
            turns[-1] = (turns[-1][0], seg["end"], spk)
        else:
            turns.append((seg["start"], seg["end"], spk))
    return turns


def transcribe(audio_path, model=None, language=None, glossary=None, diarize=True):  # pragma: no cover - needs the 21 GB model
    binary = executable()
    if not binary:
        raise FileNotFoundError("nemo-speech is missing; see references/local-backends.md")
    probe = subprocess.run([binary, "transcribe", "--help"], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if not supports_salm(probe.stdout):
        raise RuntimeError(f"{binary} has no speech-LLM support; install a NeMo-Speech.cpp nightly "
                           "(66d50d9 or newer) and set SCRIBA_NEMOTRON35_BIN")
    path = model_path(model)
    if not path.is_file():
        raise FileNotFoundError(f"Nemotron 3.5 decoder GGUF not found: {path}; "
                                "set SCRIBA_NEMOTRON35_MODEL or see references/local-backends.md")
    with tempfile.TemporaryDirectory(prefix="scriba-nemotron35-") as tmp:
        output = Path(tmp) / "out.json"
        subprocess.run(build_command(binary, audio_path, path, output, language=language,
                                     glossary=glossary, diarize=diarize), check=True)
        data = json.loads(output.read_text())
    segments = to_segments(data)
    if not segments:
        raise RuntimeError("Nemotron 3.5 produced no words")
    for seg in segments:
        print(f"Transcript: [{seg['start']:.3f} --> {seg['end']:.3f}] {seg['text']}", flush=True)
    languages = data.get("languages") or []
    return {"segments": segments, "language": language or (languages[0] if languages else None)}
