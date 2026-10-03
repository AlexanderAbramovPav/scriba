<p align="center">
  <img src="docs/scriba-logo.png" alt="scriba" width="240">
</p>

<h1 align="center">scriba</h1>

<p align="center">
  <b>Fast local meeting transcription with speaker diarization — for your AI assistant or second brain.</b><br>
  Russian GigaAM v3, multilingual WhisperX, and Nemotron 3 speaker diarization across languages, with pyannote fallback. Get Markdown, word timestamps, and voice clips through Claude Code, Codex, Cursor, Aider &amp; others via <a href="./AGENTS.md"><code>AGENTS.md</code></a>, or run the plain CLI. Audio processing stays on your computer. Optional punctuation uses the AI in your current chat, with validation that preserves the recognized words.
</p>

<p align="center">
  <a href="https://github.com/AlexanderAbramovPav/scriba/actions/workflows/ci.yml"><img alt="tests" src="https://github.com/AlexanderAbramovPav/scriba/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/AlexanderAbramovPav/scriba/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/AlexanderAbramovPav/scriba?style=flat&logo=github&label=Stars"></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green"></a>
  <img alt="macOS · Apple Silicon" src="https://img.shields.io/badge/macOS-Apple_Silicon-black?logo=apple&logoColor=white">
  <img alt="audio processed on-device" src="https://img.shields.io/badge/audio-on--device-orange">
  <img alt="99+ languages" src="https://img.shields.io/badge/languages-99%2B-blue">
  <a href="./AGENTS.md"><img alt="works with any AI agent via AGENTS.md" src="https://img.shields.io/badge/works_with-any_AI_agent-8A2BE2"></a>
</p>

## Contents
- [Why](#why)
- [How this compares](#how-this-compares)
- [What you'll get](#what-youll-get)
- [Install](#install)
- [Usage](#usage)
- [Limitations](#limitations)
- [Advanced — for power users](#advanced--for-power-users)
- [License](#license) · [Acknowledgments](#acknowledgments)

## Why

- **Audio processing stays local.** Speech recognition and speaker diarization run on your Mac (or Linux box). The optional host-AI punctuation step reads transcript text in your current AI session and follows that session's privacy and usage settings; skip it for a fully local CLI workflow.
- **Works with anything.** Zoom recordings, voice memos, podcast files, phone call exports — `.mp4`, `.mov`, `.m4a`, `.mp3`, `.wav`, `.webm`, you name it. The skill handles the format conversion for you.
- **The same diarization route for every language.** Installed [Nemotron 3](https://huggingface.co/nvidia/Nemotron-3-Diarization) is selected automatically for Russian, English, German and other ASR languages, including auto-detection. It supports up to eight speakers. [Pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) remains available for fallback, an exact speaker count, or known-voice enrollment. Equal quality across languages is not assumed: [measure it on your labeled audio](./benchmarks/) with `scripts/benchmark_der.py`.
- **Fast Russian ASR, multilingual Whisper for other languages.** An installed [GigaAM v3 RNNT](https://github.com/salute-developers/GigaAM) bundle is selected with `--lang ru`; WhisperX turbo is the Apple Silicon default otherwise. `--accurate` retains full Whisper large-v3. [Setup and model limits](./references/local-backends.md).
- **Readable text without rewriting the conversation.** Your current AI can add punctuation and sentence case. The [validator](./references/punctuation.md) rejects changed words, numbers or repetitions; raw files and speaker/timing evidence are preserved.
- **You can actually see it working.** Live progress in your editor's statusline, in a side terminal, or as a macOS notification when it's done — pick what you like. No more staring at a black screen wondering if it's stuck.
- **Just one command.** No setup steps to learn. The assistant walks you through anything you don't have yet (HuggingFace account, etc.) in plain language.
- **Built to be run automatically.** Point a `launchd`/`cron` watcher at your Zoom or Meet recordings folder — every call becomes a searchable transcript that flows into your **second brain / personal AI knowledge base** (Obsidian, Notion, Cognee, mem0, whatever you use). The more conversations you capture and feed your assistant, the sharper its answers about *you* get. See [Karpathy on personal Wikis](https://x.com/karpathy/status/1655994367033524225) for the broader idea.

## How this compares

|                                       | scriba | Otter / Fireflies / Granola | Local Whisper alone |
| ------------------------------------- | :----------------: | :-------------------------: | :-----------------: |
| Audio stays on your computer          |        ✅          |             ❌              |         ✅          |
| Tells you who said what                                  |        ✅          |             ✅              |         ❌          |
| Tells you who said what — *and how sure it is*           |        ✅          |             ❌              |         ❌          |
| Cost after install                    | **$0 for local pipeline; optional AI session usage** | $10–30/mo | $0 |
| Works offline                         |        ✅          |             ❌              |         ✅          |

*"…and how sure it is"*: timed words in the JSON sidecar carry an ASR
confidence when the backend provides one (otherwise `null`), a speaker-attribution
margin, and an overlap flag, so your AI
knows which lines to trust and which to treat as shaky. And you can put a number
on the diarization itself — [`benchmarks/`](./benchmarks/) ships a pure-Python
DER scorer you run on your own labeled audio.

## What you'll get

A portable `<title>.transcript/` folder next to your input video, holding the Markdown plus its assets, with **a 10-second voice clip per speaker** embedded right in the file (click ▶ to play in Obsidian / VS Code / GitHub):

```markdown
# q3-planning-sync

## Speakers — identify who's who

**Speaker 1** (80% of speaking time).
<audio controls src="data/speaker-1.wav"></audio>

Sample utterances:
> [00:00:03] «So the launch is moved to Friday — can we ship the docs by Thursday?»
> [00:00:40] «...»

**Speaker 2** (18% of speaking time).
<audio controls src="data/speaker-2.wav"></audio>
...
```

The assistant then asks you "who's Speaker 1?" — you answer, and it renames them everywhere in the transcript.

## Install

```bash
git clone https://github.com/AlexanderAbramovPav/scriba ~/.claude/skills/scriba
```

The first run bootstraps the Python environment and downloads model weights.
For the pyannote path, the assistant guides you through accepting the model terms
and storing a HuggingFace read token. Installed Nemotron needs no token.
The optional [native-backend setup](./references/local-backends.md#reproduce-this-installation)
enables Nemotron diarization for all languages; the [Russian bundle setup](./references/setup.md#one-time-setup-1)
enables GigaAM v3 RNNT. Both are reused on later runs.

> *Why HuggingFace?* It's the open-source equivalent of an app store for AI models. The speaker-recognition model is free, but its authors require accepting a usage agreement once — pretty standard for research-grade open source.

### Don't use Claude Code? Use it with anything else

The core of `scriba` is a bash + Python pipeline. The "skill" layer is a thin wrapper that helps an AI agent guide you through setup and speaker naming — and there's a tool-agnostic version of those instructions in [`AGENTS.md`](./AGENTS.md), supported by most modern AI coding tools.

| Your tool                       | Where to point it                                                            | How to invoke                            |
| ------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------- |
| **Claude Code**                 | clone into `~/.claude/skills/scriba/` *(default install command above)*       | `/scriba <file>`                         |
| **OpenAI Codex CLI**            | clone anywhere, place `AGENTS.md` at `~/.codex/AGENTS.md` *(or project root)* | "transcribe this meeting: `<file>`"      |
| **Cursor**                      | clone anywhere, copy `AGENTS.md` to `.cursor/rules/scriba.md`                 | mention `@scriba` or natural language     |
| **Continue.dev**                | clone anywhere, register `transcribe.sh` as a custom slash command in `~/.continue/config.yaml` | `/scriba <file>` |
| **Aider**                       | clone anywhere, `aider --read <scriba>/AGENTS.md <file>`                     | natural language in chat                  |
| **Goose** (Block)               | clone anywhere, add as a shell-command extension                             | mention scriba in chat                   |
| **ChatGPT / Claude.ai browser** | open `AGENTS.md`, paste into a "Custom Instructions" or project-context slot | tell the chat the local file path        |
| **No AI at all**                | clone anywhere                                                                | `bash <scriba>/scripts/transcribe.sh <file>` |

`AGENTS.md` is becoming a de-facto standard for cross-tool AI agent instructions — same role as `SKILL.md` but vendor-neutral. The bash CLI works in any environment, with or without an AI driving it.

## Usage

Easiest path is Claude Code (other agents & the plain CLI: see [Use it with anything else](#dont-use-claude-code-use-it-with-anything-else) above). Open Claude Code, type:

```
/scriba /path/to/your-meeting.mp4
```

Now you can walk away. The assistant runs the transcription in the background. While it's working:

- **Live status** is visible inline in your chat statusline (something like `🎙 tx 47% · ETA 01:18`), updated every few seconds.
- **A macOS notification** pops up when it's done (Glass sound).
- Or open a side terminal and run the same command with `--watch` for a full-screen progress view.

<p align="center">
  <img src="docs/scriba-screen.png" alt="scriba live progress in Claude Code's Shell details" width="900">
</p>
<p align="center"><sub>Live progress streams right into Claude Code's “Shell details” — current stage, % and ETA update as it runs (even while diarization is quiet).</sub></p>

When it finishes, the assistant adds validated punctuation to punctuation-free
output and opens the reading version, preserving the raw files. It also shows
you the speakers it found. For each one you get:
- A **short voice clip** (~10 seconds, click play in the chat / your editor — `<audio>` is embedded right in the Markdown).
- **Three sample sentences** with timestamps.

The assistant asks "who is who?" — you answer (e.g. "Speaker 1 is Alice, Speaker 2 is Bob") — it renames them everywhere in the transcript. Done.

## Where files go

Each recording becomes a self-contained, portable folder next to your input file:

```
your-meeting.transcript/      ← move/zip/sync this whole folder; nothing breaks
├── your-meeting.md           ← the transcript (H1 title + frontmatter)
├── your-meeting.punctuated.md ← optional host-AI reading version
└── data/
    ├── transcript.json       ← rich machine-readable sidecar (per-word confidence, speakers)
    ├── transcript.punctuated.json ← optional punctuation copy, raw words/times retained
    └── speaker-1.wav …       ← one ≤10 s voice clip per speaker, embedded in the MD
```

The MD points at `data/…` with **relative** paths, so the folder travels as a unit — open `your-meeting.md` in any Markdown viewer (Obsidian, VS Code, GitHub) and the embedded `<audio>` players just work.

The **folder/file name is meaningful**: it's derived from your video's name (kebab-cased). When the source name is generic (`zoom_0`, `GMT20260605-120000`, `recording`, …), the assistant picks a real title for you. The original filename is always preserved in the `source:` frontmatter field.

Alongside your recordings, a hidden **`.scriba/`** folder holds corpus-wide state your AI uses to navigate everything: `index.json` (one entry per recording — read once, find any meeting), plus the glossary and persistent voiceprints. Full layout in [`references/file-layout.md`](./references/file-layout.md).

## Beyond one-off meetings — run it automatically

The slash-command flow is the easy path. If you want every conversation captured automatically, point a small watcher at whatever folder your meeting tool dumps recordings into:

```bash
# Watch ~/Documents/Zoom/, transcribe new .m4a or .mp4 files
fswatch -0 ~/Documents/Zoom | while read -d '' f; do
  case "$f" in *.m4a|*.mp4)
    bash ~/.claude/skills/scriba/scripts/transcribe.sh "$f" ;;
  esac
done
```

Then point your second-brain tool (Obsidian, Cognee, mem0, Notion AI, …) at the `*.transcript/*.md` files and you have a personal, private, searchable corpus of everything that's been said in your meetings — feeding back into AI assistants the way [Karpathy described a personal Wiki](https://x.com/karpathy/status/1655994367033524225). The more conversations the assistant can reach, the more it sounds like *you* and the better it answers questions about *your* world.

## Limitations

- Two speakers who sound similar (e.g. brothers, or two soft-spoken voices) may be merged into one.
- Heavy background music or three+ people speaking simultaneously degrades speaker boundaries.
- Apple Silicon strongly recommended. Intel Macs work but are ~3× slower; Linux works (no macOS notification, no MLX fast-mode).
- First run downloads ~3 GB of models — plan accordingly on metered connections.
- Diarization routing is shared across languages. A real Russian call and synthetic English/German dialogues were checked; quality has not been measured against human speaker labels across all languages.
- Nemotron handles at most eight speakers. Use `--diarizer pyannote` for larger groups, `--speakers N`, or known-voice enrollment.
- Host-AI punctuation takes extra chat time/tokens and can affect interpretation. It does not repair ASR spelling or speaker errors, and is absent from unattended CLI-only runs.

---

## Advanced — for power users

Everything below is optional. The slash command flow above is what 99% of people need.

See [local backend notes](references/local-backends.md) for Apple Silicon routing,
model limits and installation. The October 2026 Oscar test compared five-minute
clips using the same Mac; GigaAM v3 RNNT + Nemotron processed 31:00–36:00 in
31.3 s, versus 416.8 s for the original CPU large-v3 + pyannote pipeline (13.3×).
This is a speed measurement, not a ground-truth WER/DER accuracy claim. RNNT
provides Russian spelling without punctuation; the AI driving the skill restores
punctuation and sentence case in a separate readable version, with a validator
that preserves words, numbers and speaker/timing evidence. No extra API key or
model is needed. See [host-AI punctuation](references/punctuation.md).
Retain full Whisper for ASR review.

### Run the bash directly

```bash
bash scripts/transcribe.sh <media-file> [--fast] [--speakers N] [--lang XX] [--model M]
```

| Flag | Meaning |
|---|---|
| (default) | `--lang ru` with installed bundle: GigaAM v3 RNNT. Otherwise WhisperX large-v3-turbo on Apple Silicon. Nemotron 3 when installed, else pyannote MPS/CPU. |
| `--fast` | Experimental MLX/native timing; review phrase completeness on Russian audio. |
| `--accurate` | Full large-v3 with the original WhisperX decoder and forced alignment. |
| `--asr gigaam3` | Optional Russian GigaAM v3 E2E CTC on MPS. |
| `--diarizer auto/pyannote/nemotron` | Explicit local diarizer selection. Nemotron supports up to eight voices; enrollment/count hints use pyannote. |
| `--speakers N` | Hint the number of speakers (helps pyannote when audio is short or noisy). Default: auto. |
| `--lang XX` | Force ISO language code (`en`, `ru`, `de`, …). Default: auto-detect. |
| `--model M` | Override the Whisper/GigaAM3 model. Explicit model overrides select WhisperX unless `--asr` is supplied. |
| `--bootstrap` | Just create the venv, don't transcribe. |
| `--status <file>` | Print a one-line progress summary (cheap to poll). |
| `--watch <file>` | Full-screen TUI watcher (run in a side terminal). |

Speaker renaming after the fact:
```bash
python3 scripts/rename_speakers.py meeting.transcript/meeting.md "Alice,Bob,Carol"
# or explicit mapping:
python3 scripts/rename_speakers.py meeting.transcript/meeting.md --map "Speaker 1=Alice,Speaker 2=Bob"
```

### Monitoring surfaces

Pick the channel that fits your workflow. All read the same source of truth (`*.transcript.progress.json` next to the input — auto-deleted on successful completion together with `*.transcript.log`, so you're left with only the human-facing `<title>.transcript/` folder. Diagnostic files are kept only when something fails).

| Surface | What you do | What you see |
|---|---|---|
| **Statusline integration** | Wire `scripts/statusline.sh` into your Claude Code / tmux / Starship / p10k statusline once. Recipes: [`references/statusline-integration.md`](./references/statusline-integration.md). | `🎙 tx 47%* · ETA 01:18` → `🎙 dia/embedd 50%* · 02:17` → empty. Refreshes every ~3 s in your normal status bar. Zero AI tokens. |
| **`--watch` TUI** | `bash scripts/transcribe.sh --watch /path/to/file.mp4` in a side terminal. | Full-screen progress bar, audio %, ETA, last log line. 2 s refresh. Ctrl-C detaches; transcription keeps running. |
| **`--status` one-liner** | `bash scripts/transcribe.sh --status /path/to/file.mp4` | One line: `stage=transcribe · elapsed 02:30 · ETA 01:18 (observed) · audio 47% (measured) · wall 51% · …` |
| **`*.transcript.progress.json`** | Read the file directly. | Compact JSON (~350 B) with the canonical schema (see [`references/eta-factors.md`](./references/eta-factors.md)). Refreshed every 5 s. |
| **macOS notification** | Nothing — fires automatically on `done` if `osascript` is available. | Notification Center card "scriba · <file> · <wall-clock>" with the Glass sound. |
| **`*.transcript.log`** | `tail -f /path/to/file.transcript.log` | Raw whisperX + pyannote output, including each per-segment `Transcript: [start --> end] text` line and each `diarize/<step> N% (X/Y)` progress event. |

### Performance — how long will it take?

> The following factors describe the historical CPU large-v3 + pyannote path. New backend measurements are in [local backends](references/local-backends.md); calibration is kept separately by pipeline.

**Rule of thumb: a 1-hour recording takes roughly 1 hour on an M4 Max, ~1.5 h on an M2 Max, ~2 h on an M1.** First run is slower (~5 min one-time model download); after that, the skill auto-calibrates to your machine's actual speed and the next ETA is anchored to *your* measured rate.

The model: `wall_clock ≈ audio_sec × factor + warmup`, where **`factor`** is the wall-clock-per-audio-second ratio for the full pipeline (transcribe + align + diarize). Anchored to one observed M4 Max run = 1.0× (Jun 2026, `batch_size=1`, `int8` compute_type). Other chips scaled from public CPU benchmarks — starting estimates only; the calibration cache at `~/.config/scriba/calibration.json` replaces the value with the actual observed rate after the first ≥60 s run.

| Chip | `factor` | Rough wall-clock for 1 h of audio |
|---|---:|---:|
| M1 | 2.0× | ~2 h |
| M1 Pro | 1.7× | ~1.7 h |
| M1 Max | 1.5× | ~1.5 h |
| M1 Ultra | 1.3× | ~1.3 h |
| M2 | 1.7× | ~1.7 h |
| M2 Pro | 1.5× | ~1.5 h |
| M2 Max | 1.3× | ~1.3 h |
| M2 Ultra | 1.2× | ~1.2 h |
| M3 | 1.5× | ~1.5 h |
| M3 Pro | 1.3× | ~1.3 h |
| M3 Max | 1.2× | ~1.2 h |
| M4 | 1.3× | ~1.3 h |
| M4 Pro | 1.1× | ~1.1 h |
| **M4 Max** | **1.0×** | **~1 h** ← anchor |
| `--fast` (MLX, any Apple Silicon) | ~0.5× | ~30 m |

Intel and unknown CPUs fall back to `2.0×`. Linux works (degraded: no macOS notification, no native MLX) — same factor table applies, the cache corrects after the first run.

**Have a chip not in this table, or a measurably different rate?** See [`CONTRIBUTING.md`](./CONTRIBUTING.md) — adding a row is a one-line PR.

### How it works

1. `transcribe.sh` extracts the input to 16 kHz mono WAV via ffmpeg.
2. `transcribe_whisperx.py` runs the selected ASR backend (GigaAM, WhisperX, or experimental MLX). It retains word timing and emits segment progress where the backend supports it.
3. The shared resolver selects Nemotron or pyannote independently of language. Nemotron runs through the local native CLI; pyannote runs with `TextProgressHook` so its sub-steps report real `completed/total` counters. Both feed word-level speaker assignment, short-turn reconciliation and uncertainty flags.
4. A bash ticker scans the log every 5 s and writes the canonical `*.progress.json`.
5. All monitoring surfaces read that one JSON.
6. On exit, `json_to_md.py` turns the JSON into Markdown inside `<title>.transcript/`, ffmpeg cuts one ≤10 s WAV clip per speaker into its `data/` folder for the embedded `<audio>` players, the JSON sidecar is copied there too, and `update_index.py` upserts the recording into `.scriba/index.json`. See [`references/file-layout.md`](./references/file-layout.md).
7. When an AI is driving the skill, it can restore punctuation through `punctuate.py` and render a separate reading version using the existing clips. This step is outside the local pipeline and its ETA.

## License

[MIT](./LICENSE) — © 2026 [Alexander Abramov](https://github.com/AlexanderAbramovPav).
Source & issues: <https://github.com/AlexanderAbramovPav/scriba>

Runtime dependencies (whisperX, pyannote.audio, faster-whisper, CTranslate2, OpenAI Whisper, ffmpeg) are installed locally, not vendored. Their licenses are catalogued in [`THIRD_PARTY_LICENSES.md`](./THIRD_PARTY_LICENSES.md).

**Pyannote attribution**: when using `pyannote/speaker-diarization-community-1`, retain its [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) attribution:

> Speaker diarization powered by [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) by Hervé Bredin / pyannoteAI, licensed under CC-BY-4.0.

## Acknowledgments

Scriba builds on these projects:

- [**whisperX**](https://github.com/m-bain/whisperX) — Max Bain et al. — word-level alignment + diarization orchestration on top of faster-whisper.
- [**pyannote.audio**](https://github.com/pyannote/pyannote-audio) — Hervé Bredin et al. — neural speaker diarization.
- [**faster-whisper**](https://github.com/SYSTRAN/faster-whisper) — SYSTRAN — the actual ASR engine, CTranslate2-backed.
- [**OpenAI Whisper**](https://github.com/openai/whisper) — OpenAI — the acoustic model.
- [**GigaAM**](https://github.com/salute-developers/GigaAM) — Salute developers — Russian speech recognition.
- [**sherpa-onnx**](https://github.com/k2-fsa/sherpa-onnx) — ONNX ASR runtime.
- [**NeMo-Speech.cpp**](https://github.com/NVIDIA/NeMo-Speech.cpp) and [**Nemotron 3 Diarization**](https://huggingface.co/nvidia/Nemotron-3-Diarization) — NVIDIA — native speaker diarization.
- [**MLX Whisper**](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — experimental Apple GPU ASR.

And on [`uv`](https://github.com/astral-sh/uv) (Astral) for the bootstrap, and [`ffmpeg`](https://ffmpeg.org/) for everything audio-shaped.
