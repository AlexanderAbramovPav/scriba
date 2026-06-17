# ADR: Adopting faster-whisper as a direct ASR backend

- **Status:** Rejected (no action) — 2026-06-17
- **Context:** SYSTRAN/faster-whisper (CTranslate2 reimplementation of Whisper) was proposed as a
  way to speed up / improve scriba's transcription.

## Decision

**Do not add faster-whisper as a direct backend. scriba already uses it — transitively, through
whisperX — and that is the right level of integration.**

## Why

1. **It's already the engine.** whisperX's ASR path *is* faster-whisper. The skill venv ships
   `faster-whisper 1.2.1` + `ctranslate2 4.7.2` as whisperX dependencies, and `whisperx.load_model()`
   instantiates faster-whisper's CT2 `WhisperModel`. `scripts/transcribe_whisperx.py` already knows
   this (it passes `hotwords` only when faster-whisper's signature supports it). So scriba's default
   accuracy path runs on faster-whisper today.

2. **A direct integration buys nothing on quality/speed.** Same CT2 engine and weights → identical
   decode speed and WER. There is no faster path hiding underneath.

3. **It would *cost* accuracy.** scriba's diarization, word↔speaker reconciliation, per-word
   confidence and enrollment (C1/C2/C3) all depend on whisperX's **wav2vec2 forced alignment** for
   word timestamps, which is more accurate than faster-whisper's native DTW timestamps. Going
   "direct" means re-adding `whisperx.align` anyway, so the whisperX dependency stays — for less.

4. **faster-whisper's headline edge doesn't apply here.** Its `BatchedInferencePipeline` (v1.1+)
   speeds up batched VAD-chunked decoding, but scriba intentionally runs `batch_size=1` so each
   segment streams to the live progress ticker as it's decoded. Batching would trade that UX away.

5. **More surface to maintain.** scriba already has three ASR routes (whisperX-CPU, whisply/MLX for
   `--fast`, GigaAM-RU opt-in). A fourth, redundant one is net negative.

## The one good adjacent idea

The genuinely useful thought behind "adopt faster-whisper directly" is **decoupling ASR from the
pyannote-pinned diarization stack** — the coupling that caused [issue #3](https://github.com/AlexanderAbramovPav/scriba/issues/3),
where whisply's `pyannote.audio==3.4.0` pin broke the community-1 pipeline. That is solved by
**pinning pyannote independently** (the bootstrap now upgrades to `pyannote.audio>=4.0`), not by
swapping the ASR engine.

## Revisit if

- whisperX becomes unmaintained or stops tracking new Whisper / pyannote releases, **or**
- we decide to drop whisperX entirely — in which case faster-whisper (ASR) + a standalone wav2vec2
  aligner + independently-pinned pyannote (diarization) would be the clean decomposition.
