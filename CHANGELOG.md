# Changelog

All notable changes to **scriba** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-06-06

First public release.

### Added
- Local, speaker-diarized Markdown transcription — **whisperX large-v3** + **pyannote `community-1`**, 100% on-device, no cloud.
- **Word↔speaker boundary reconciliation** — segments are split at word-level speaker changes, so the words around a turn are attributed to the right person instead of the segment majority.
- **Honest uncertainty** — per-word `asr_conf` / `overlap` / `speaker_conf` plus a persisted, schema-versioned `transcript.json` sidecar designed as clean input for an AI/second brain; a light `⚠︎` marker and `low_confidence_pct` surface it in the Markdown without clutter.
- **Glossary biasing** — domain terms (product names, jargon, mixed RU/EN) feed `initial_prompt`/`hotwords` from a project (`.scriba/glossary.txt`) over global glossary.
- **Known-speaker enrollment** — `--enroll "Name=clip.wav"` matches diarized clusters to known voices via community-1 embeddings.
- **Optional GigaAM-RU backend** — `--asr gigaam` (sherpa-onnx ONNX), ~−50% WER on Russian vs Whisper; strictly opt-in, default path unchanged.
- **Portable per-recording layout** — `<title>.transcript/{<title>.md, data/}` with a hidden `.scriba/` for the corpus index, glossary and voiceprints; meaningful filenames auto-derived from the source (agent fallback for generic names).
- **Live progress** — statusline integration, `--watch` TUI, macOS notification, and a stdout heartbeat that keeps Claude Code's "Shell details" current during long runs.
- **Self-contained DER benchmark** — `scripts/benchmark_der.py`, pure-Python (zero third-party deps).
- **Agent-agnostic** — works with Claude Code, Codex, Cursor, Aider and others via `AGENTS.md`, or as a plain CLI with no AI at all.
- Continuous integration (GitHub Actions: `pytest` on Python 3.11 and 3.12).

[Unreleased]: https://github.com/AlexanderAbramovPav/scriba/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AlexanderAbramovPav/scriba/releases/tag/v0.1.0
