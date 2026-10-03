"""Local Nemotron 3 (up to eight speakers) via NVIDIA NeMo-Speech.cpp."""
from __future__ import annotations

import math
import os
from pathlib import Path
import shutil
import subprocess


def select_backend(requested="auto", *, num_speakers=None, enroll=None):
    """Choose a diarizer independently of ASR language and backend."""
    if requested not in {"auto", "nemotron", "pyannote"}:
        raise ValueError(f"Unknown diarizer: {requested}")
    if num_speakers is not None and num_speakers <= 0:
        raise ValueError("Speaker-count hint must be positive")
    needs_pyannote = bool(enroll) or num_speakers is not None
    if requested == "nemotron" and needs_pyannote:
        raise ValueError("Nemotron does not support enrollment or an exact speaker-count hint; use --diarizer pyannote")
    if requested == "pyannote" or needs_pyannote:
        return "pyannote"
    binary = executable()
    if requested == "nemotron" and not binary:
        raise FileNotFoundError("nemo-speech is missing; see references/local-backends.md")
    return "nemotron" if binary else "pyannote"


def executable() -> str | None:
    explicit = os.environ.get("SCRIBA_NEMO_BIN")
    if explicit:
        if not (Path(explicit).is_file() and os.access(explicit, os.X_OK)):
            raise FileNotFoundError(f"SCRIBA_NEMO_BIN is not executable: {explicit}")
        return explicit
    return shutil.which("nemo-speech")


def parse_rttm(text: str) -> list[tuple[float, float, str]]:
    turns = []
    for line in text.splitlines():
        cols = line.split()
        if not cols or cols[0] != "SPEAKER":
            continue
        if len(cols) < 8:
            raise ValueError("Malformed Nemotron RTTM row")
        start, duration = float(cols[3]), float(cols[4])
        if not (math.isfinite(start) and math.isfinite(duration)) or start < 0 or duration <= 0:
            raise ValueError("Invalid Nemotron turn timing")
        turns.append((start, start + duration, cols[7]))
    return sorted(turns)


def diarize(audio_path: str, device="auto", num_speakers=None):
    if num_speakers is not None and num_speakers > 8:
        raise ValueError("Nemotron 3 supports up to 8 speakers; use --diarizer pyannote")
    binary = executable()
    if not binary:
        raise FileNotFoundError("nemo-speech is missing; see references/setup.md")
    # Large streaming chunks preserve speaker identity over recordings of any length.
    # --offline full attention is limited to ~6.6 minutes and is deliberately avoided.
    native_device = "metal" if device == "mps" else device
    command = [binary, "diarize", str(audio_path), "--model", "nemotron-diar",
               "--preset", "v3-offline", "--device", native_device, "--format", "rttm"]
    done = subprocess.run(command, text=True, stdout=subprocess.PIPE, check=True)
    turns = parse_rttm(done.stdout)
    if not turns:
        raise RuntimeError("Nemotron produced no speaker turns")
    return turns


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Resolve the shared language-independent diarization backend")
    parser.add_argument("--backend", default="auto")
    parser.add_argument("--num-speakers", type=int)
    parser.add_argument("--enroll")
    args = parser.parse_args()
    try:
        print(select_backend(args.backend, num_speakers=args.num_speakers, enroll=args.enroll))
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
