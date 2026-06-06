#!/usr/bin/env python3
"""Run whisperX directly with per-segment progress streaming.

Replaces the `whisply run` CLI call for the CPU path so we can:
- print `Transcript: [<start> --> <end>] <text>` as each segment is decoded
  (the ticker parses this to compute REAL audio %, not a chip-factor extrapolation),
- keep alignment + pyannote diarization,
- emit a JSON whose shape json_to_md.py already groks (flat whisperX form).

MLX (`--fast`) still routes through whisply because whisperX-py doesn't have
a native MLX backend.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import warnings
from pathlib import Path

# Make the sibling module (diarize_reconcile) importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Belt-and-braces: even if the caller forgets `python -u`, force line-buffered
# stdout/stderr so each whisperX `Transcript: [...]` print flushes at its newline.
# Without this, piping to tee makes Python block-buffer 4 KB before flushing,
# and the live ticker sees nothing until the entire transcribe stage finishes.
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Silence noisy non-fatal warnings BEFORE importing whisperX (torchaudio
# deprecation, pyannote/torch version mismatch, etc.). They otherwise show up
# in the live log and crowd the ticker's `last_log` field.
warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("pyannote").setLevel(logging.ERROR)
logging.getLogger("speechbrain").setLevel(logging.ERROR)
# Lightning 2.x split the package: legacy `pytorch_lightning` AND new `lightning.pytorch.*`.
# Silence both — and `lightning_fabric` — to suppress the "Lightning automatically upgraded
# your loaded checkpoint from vX to vY" info notice that fires every run.
logging.getLogger("pytorch_lightning").setLevel(logging.ERROR)
logging.getLogger("lightning").setLevel(logging.ERROR)
logging.getLogger("lightning.pytorch").setLevel(logging.ERROR)
logging.getLogger("lightning_fabric").setLevel(logging.ERROR)

import whisperx  # noqa: E402


class TextProgressHook:
    """pyannote.audio hook adapter — emits plain-text progress lines to stderr.

    pyannote calls this from each internal step (segmentation, embedding extraction,
    clustering, …) with `completed/total` integer counters. We turn that into lines
    like `→ diarize/segmentation 47% (12/26)` that the bash ticker can grep for and
    surface as real progress in the statusline.

    We deliberately emit only on 10% boundaries (and at 0% / 100%) — otherwise
    pyannote's per-frame updates would spam the log with hundreds of lines.
    """

    def __enter__(self) -> "TextProgressHook":
        self._last_step: str | None = None
        self._last_bucket: int = -1
        return self

    def __exit__(self, *exc) -> None:
        pass

    def __call__(self, step_name, step_artifact=None, file=None, total=None, completed=None):
        if completed is None:
            completed, total = 1, 1
        # New step → reset bucket and announce.
        if step_name != self._last_step:
            self._last_step = step_name
            self._last_bucket = -1
            print(f"→ diarize/{step_name} starting", file=sys.stderr, flush=True)
        if not total:
            return
        pct = int(completed * 100 / total)
        bucket = pct // 10
        if bucket != self._last_bucket or completed >= total:
            self._last_bucket = bucket
            print(f"→ diarize/{step_name} {pct}% ({completed}/{total})",
                  file=sys.stderr, flush=True)


def log(msg: str) -> None:
    """Status line to stderr. Goes into the .transcript.log via the shell's tee."""
    print(f"→ {msg}", file=sys.stderr, flush=True)


class Heartbeat:
    """Print a periodic 'still working' line while a long blocking call is in flight.

    pyannote's diarization and whisperX's alignment-model load can each take 30+ s
    with zero output. Without a heartbeat the log looks frozen and the user thinks
    it hung. We emit a line every `interval` seconds with elapsed time.
    """

    def __init__(self, label: str, interval: float = 10.0):
        self._label = label
        self._interval = interval
        self._stop = threading.Event()
        self._t0 = 0.0
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            elapsed = int(time.time() - self._t0)
            log(f"{self._label}… ({elapsed}s)")

    def __enter__(self) -> "Heartbeat":
        self._t0 = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="path to 16kHz mono WAV")
    ap.add_argument("--output", required=True, help="path to write result JSON")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--asr", default="whisperx", choices=["whisperx", "gigaam"],
                    help="ASR backend. gigaam = Russian-optimized (sherpa-onnx), opt-in.")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    ap.add_argument("--language", default=None)
    ap.add_argument("--batch-size", type=int, default=1,
                    help="whisperX batch size. 1 = smoothest per-segment streaming on CPU. "
                         "Larger values can be faster on GPU but stall progress until the batch finishes.")
    ap.add_argument("--glossary", default=None,
                    help="comma-separated bias terms (initial_prompt/hotwords)")
    ap.add_argument("--annotate", action="store_true", help="run pyannote diarization after transcription")
    ap.add_argument("--hf-token", default=None)
    ap.add_argument("--num-speakers", type=int, default=None)
    ap.add_argument("--enroll", default=None,
                    help='comma list "Name=clip.wav" to match known voices')
    args = ap.parse_args()

    # ASR backend selection. The default whisperX path is below as the `else`; the
    # opt-in GigaAM-RU path is model-dependent (sherpa-onnx + ONNX bundle) and so is
    # excluded from coverage. BOTH branches must define `audio`, `audio_sec`,
    # `language`, and `result` so the shared diarization/reconcile/confidence code
    # below runs unchanged.
    if args.asr == "gigaam":  # pragma: no cover - needs sherpa-onnx + GigaAM model
        import asr_gigaam
        log(f"loading audio: {args.audio}")
        audio = whisperx.load_audio(args.audio)
        audio_sec = len(audio) / 16000.0
        log(f"GigaAM-RU ASR (sherpa-onnx) on {audio_sec:.1f}s ({audio_sec/60:.1f}m)")
        ga = asr_gigaam.transcribe(args.audio)
        language = args.language or "ru"
        if ga.get("needs_alignment"):
            log("GigaAM gave no word timestamps; aligning text with wav2vec")
            # normalize_segments emits start=end=0.0 when no timestamps; whisperx.align
            # crops audio[int(start*SR):int(end*SR)] per segment, so a zero-width window
            # would starve the aligner. Widen to span the whole recording first.
            for seg in ga["segments"]:
                seg["start"] = 0.0
                seg["end"] = audio_sec
            try:
                with Heartbeat("alignment in progress"):
                    align_model, metadata = whisperx.load_align_model(
                        language_code=language, device=args.device)
                    result = whisperx.align(
                        ga["segments"], align_model, metadata, audio, args.device,
                        return_char_alignments=False)
                del align_model
                log(f"alignment done: {len(result.get('segments', []))} aligned segments")
            except Exception as e:  # mirror the whisperX path: degrade, don't crash
                log(f"WARN: GigaAM alignment failed ({type(e).__name__}: {e}); using unaligned segments")
                result = {"segments": ga["segments"]}
        else:
            result = {"segments": ga["segments"]}
            log(f"GigaAM done: {len(result.get('segments', []))} word-timestamped segments")
    else:
        compute_type = "int8" if args.device == "cpu" else "float16"
        log(f"loading model {args.model} (device={args.device}, compute_type={compute_type})")
        model = whisperx.load_model(
            args.model,
            device=args.device,
            compute_type=compute_type,
            language=args.language,
        )

        log(f"loading audio: {args.audio}")
        audio = whisperx.load_audio(args.audio)
        audio_sec = len(audio) / 16000.0
        log(f"audio loaded: {audio_sec:.1f}s ({audio_sec/60:.1f}m)")

        # whisperX's transcribe() with verbose=True prints
        #   `Transcript: [<start> --> <end>] <text>`
        # for each segment as it's decoded. With batch_size=1 these stream one at a time;
        # larger batches buffer them until the batch finishes.
        log("transcribing (verbose: each segment streams as decoded)")
        transcribe_kwargs = dict(batch_size=args.batch_size, verbose=True, print_progress=True)
        if args.glossary:
            transcribe_kwargs["initial_prompt"] = args.glossary
            # faster-whisper >=1.0 also accepts hotwords; only pass if the signature supports it.
            try:
                import inspect
                if "hotwords" in inspect.signature(model.transcribe).parameters:
                    transcribe_kwargs["hotwords"] = args.glossary
            except (ValueError, TypeError):
                pass
        result = model.transcribe(audio, **transcribe_kwargs)
        language = result.get("language") or args.language or "en"
        raw_segments = result.get("segments") or []
        log(f"transcribe done: {len(raw_segments)} segments · lang={language}")

        # Free the ASR model before loading the alignment model — keeps CPU memory bounded.
        del model

        log("loading alignment model")
        try:
            with Heartbeat("alignment in progress"):
                align_model, metadata = whisperx.load_align_model(language_code=language, device=args.device)
                result = whisperx.align(
                    raw_segments,
                    align_model,
                    metadata,
                    audio,
                    args.device,
                    return_char_alignments=False,
                )
            del align_model
            log(f"alignment done: {len(result.get('segments', []))} aligned segments")
        except Exception as e:  # pragma: no cover - alignment is best-effort
            log(f"WARN: alignment failed ({type(e).__name__}: {e}); using unaligned segments")
            result = {"segments": raw_segments, "language": language}

    # Overlap-aware turns drive the C2 confidence signals. Default empty so the
    # enrichment below is well-defined even when diarization is skipped/no token.
    overlap_turns: list = []

    if args.annotate and args.hf_token:
        log("diarizing (pyannote/speaker-diarization-community-1)")
        try:
            # We bypass whisperX's `DiarizationPipeline.__call__` because it doesn't pass
            # through pyannote's `hook=` argument — and that hook is the ONLY way to get
            # real per-step progress (segmentation / embedding / clustering each report
            # completed/total counters). Below we reproduce the wrapper's audio prep and
            # dataframe shape, but inject our TextProgressHook so the log shows actual %.
            import pandas as pd  # whisperX already depends on pandas
            import torch
            from pyannote.audio import Pipeline as PyannotePipeline
            from whisperx.audio import SAMPLE_RATE as _SR  # 16000 in practice

            with Heartbeat("loading pyannote model"):
                # pyannote.audio 4.x default pipeline. Model is CC-BY-4.0 (attribution
                # required); see THIRD_PARTY_LICENSES.md. Users must accept the gate at
                # https://huggingface.co/pyannote/speaker-diarization-community-1 once.
                pa_pipeline = PyannotePipeline.from_pretrained(
                    "pyannote/speaker-diarization-community-1",
                    token=args.hf_token,
                ).to(torch.device(args.device))

            audio_data = {
                "waveform": torch.from_numpy(audio[None, :]),
                "sample_rate": _SR,
            }
            pa_kwargs = {}
            if args.num_speakers:
                pa_kwargs["num_speakers"] = args.num_speakers

            # No outer Heartbeat here — the hook provides finer-grained progress lines,
            # so we don't need the fallback heartbeat noise.
            with TextProgressHook() as hook:
                diarization = pa_pipeline(audio_data, hook=hook, **pa_kwargs)

            # pyannote.audio 4 + community-1 returns a `DiarizeOutput` wrapper with
            # `.speaker_diarization` (the legacy Annotation), `.exclusive_speaker_diarization`,
            # and `.speaker_embeddings`. Older 3.x pipelines just return the Annotation
            # directly. Normalise both shapes.
            annotation = getattr(diarization, "speaker_diarization", diarization)
            exclusive = getattr(diarization, "exclusive_speaker_diarization", annotation)

            # Overlap-aware turns for confidence signals (C2).
            overlap_turns = [(seg.start, seg.end, spk)
                             for seg, _, spk in annotation.itertracks(yield_label=True)]

            # Exclusive (non-overlapping) backbone for word assignment (C1/C2).
            diarize_df = pd.DataFrame(
                exclusive.itertracks(yield_label=True),
                columns=["segment", "label", "speaker"],
            )
            diarize_df["start"] = diarize_df["segment"].apply(lambda x: x.start)
            diarize_df["end"] = diarize_df["segment"].apply(lambda x: x.end)

            with Heartbeat("assigning speakers to words"):
                result = whisperx.assign_word_speakers(diarize_df, result)
            log(f"diarization done: {len(result.get('segments', []))} segments speaker-tagged")

            # C3: match clusters to known voices and rename labels by construction.
            # community-1's `speaker_embeddings` is a positional ndarray
            # (num_speakers, dim) ordered to match `annotation.labels()` — NOT a dict;
            # embeddings_to_dict zips them back into {label: vector}. The exclusive
            # (segment) diarization shares the same label SET as `annotation`, so these
            # mapping keys hit the segment/word `speaker` labels set by assign_word_speakers.
            if args.enroll:
                try:
                    import enroll as _enroll
                    cluster_embs = _enroll.embeddings_to_dict(
                        annotation.labels(), getattr(diarization, "speaker_embeddings", None))
                    ref_embs = {}
                    for pair in args.enroll.split(","):
                        name, _, clip = pair.partition("=")
                        name, clip = name.strip(), clip.strip()
                        if not (name and clip):
                            continue
                        ref_out = pa_pipeline({"waveform": torch.from_numpy(
                            whisperx.load_audio(clip)[None, :]), "sample_rate": _SR})
                        ref_arr = getattr(ref_out, "speaker_embeddings", None)
                        if ref_arr is not None and len(ref_arr):
                            ref_embs[name] = [float(x) for x in ref_arr[0]]  # single-speaker clip -> row 0
                    mapping = _enroll.match_clusters(cluster_embs, ref_embs)
                    for seg in result.get("segments", []):
                        if seg.get("speaker") in mapping:
                            seg["speaker"] = mapping[seg["speaker"]]
                        for w in seg.get("words", []):
                            if w.get("speaker") in mapping:
                                w["speaker"] = mapping[w["speaker"]]
                    if mapping:
                        log(f"enrolled: {mapping}")
                except Exception as e:  # pragma: no cover
                    log(f"WARN: enrollment skipped ({type(e).__name__}: {e})")
        except Exception as e:
            log(f"WARN: diarization failed ({type(e).__name__}: {e}); continuing without speaker labels")
    elif args.annotate and not args.hf_token:
        log("WARN: --annotate requested but no --hf-token; skipping diarization")

    # C1: split segments at word-level speaker changes (word-accurate attribution).
    try:
        import diarize_reconcile
        result = diarize_reconcile.reconcile(result)
        log(f"reconciled: {len(result.get('segments', []))} single-speaker segments")
    except Exception as e:  # pragma: no cover
        log(f"WARN: reconciliation skipped ({type(e).__name__}: {e})")

    # C2: per-word confidence/overlap signals + a light low_confidence_pct.
    # Must run AFTER reconcile so split segments carry the right per-word fields.
    try:
        import transcript_confidence
        segs, low_pct = transcript_confidence.enrich_segments(
            result.get("segments", []), overlap_turns)
        result["segments"] = segs
        result["low_confidence_pct"] = low_pct
    except Exception as e:  # pragma: no cover
        log(f"WARN: confidence enrichment skipped ({type(e).__name__}: {e})")
        result["low_confidence_pct"] = 0.0

    out = {
        "schema_version": 1,
        "language": language,
        "audio_duration_sec": round(audio_sec, 3),
        "low_confidence_pct": result.get("low_confidence_pct", 0.0),
        "segments": result.get("segments", []),
    }
    import jsonsafe
    Path(args.output).write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=jsonsafe.json_default))
    log(f"wrote JSON: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
