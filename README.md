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
  <img alt="multilingual ASR" src="https://img.shields.io/badge/ASR-multilingual-blue">
  <a href="./AGENTS.md"><img alt="works with local AI agents" src="https://img.shields.io/badge/works_with-local_AI_agents-8A2BE2"></a>
</p>

## Contents

- [Why](#why)
- [How this compares](#how-this-compares)
- [What you'll get](#what-youll-get)
- [Install](#install)
- [Usage](#usage)
- [Where files go](#where-files-go)
- [Limitations](#limitations)
- [Performance](#performance--how-long-will-it-take)
- [Advanced — for power users](#advanced--for-power-users)
- [License](#license) · [Acknowledgments](#acknowledgments)

## Why

- **Audio processing stays local.** Speech recognition and speaker diarization run on your computer. The optional host-AI punctuation step reads transcript text in your current AI session and follows that session's privacy and usage settings; skip it for a fully local CLI workflow.
- **Works with anything.** Zoom recordings, voice memos, podcast files, phone call exports — `.mp4`, `.mov`, `.m4a`, `.mp3`, `.wav`, `.webm`, you name it. The skill handles the format conversion for you.
- **The same diarization route for every language.** Installed [Nemotron 3](https://huggingface.co/nvidia/Nemotron-3-Diarization) is selected automatically for Russian, English, German and other ASR languages, including auto-detection. It supports up to eight speakers. [Pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) remains available for fallback, an exact speaker count, or known-voice enrollment. Equal quality across languages is not assumed: [measure it on your labeled audio](./benchmarks/) with `scripts/benchmark_der.py`.
- **Fast Russian ASR, multilingual Whisper for other languages.** An installed [GigaAM v3 RNNT](https://github.com/salute-developers/GigaAM) bundle is selected with `--lang ru` when no glossary or model override is requested; WhisperX turbo is the Apple Silicon default otherwise (full large-v3 on other systems). `--accurate` retains full Whisper large-v3. [Setup and model limits](./references/local-backends.md).
- **Readable text without rewriting the conversation.** Your current AI can add punctuation and sentence case. The [validator](./references/punctuation.md) rejects changed words, numbers or repetitions; raw files and speaker/timing evidence are preserved.
- **You can actually see it working.** Live progress in your editor's statusline, in a side terminal, or as a macOS notification when it's done — pick what you like. No more staring at a black screen wondering if it's stuck.
- **CLI or AI-assisted workflow.** The local pipeline runs without an AI agent. A local agent can help with setup, punctuation and identifying anonymous speaker labels.
- **Portable output for your notes and search tools.** Keep Markdown, JSON and voice clips together, or feed the transcript into your chosen knowledge-base workflow. An unattended CLI run produces raw output; AI punctuation requires an active AI session.

## How this compares

| Capability | Scriba local CLI | Scriba with a host AI | ASR alone |
|---|---|---|---|
| Audio processed locally | Yes | Yes | Yes for a local ASR engine |
| Speaker labels and voice samples | Yes, with a configured diarizer | Yes, with a configured diarizer | Requires a separate diarizer |
| Word timing and uncertainty signals | When available from the backend | Same evidence as the CLI | Depends on the engine |
| Punctuation for GigaAM RNNT output | Raw text | Validated punctuation/case edits | Depends on the model |
| Service usage | Local compute, no per-minute service fee | Local compute + current AI-session usage | Depends on the engine |
| Offline operation | After weights and dependencies are installed | Local speech pipeline; AI depends on its environment | Depends on the engine |

Timed words carry an ASR score when the backend provides one (otherwise `null`),
a speaker-attribution margin and an overlap flag after successful diarization.
These are uncertainty signals, not measured word/speaker accuracy. The
[`benchmarks/`](./benchmarks/) DER scorer uses raw diarizer turns against your
checked speaker labels.

## What you'll get

A portable `<title>.transcript/` folder next to your input video, holding the Markdown plus its assets, with **one voice clip per speaker, up to 10 seconds**. The Markdown embeds an HTML audio player for viewers that support local audio; otherwise open the WAV directly:

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

The assistant asks who the anonymous speakers are, then renames their display labels in the Markdown. The JSON sidecars retain their source labels.

## Install

```bash
git clone https://github.com/AlexanderAbramovPav/scriba ~/.claude/skills/scriba
```

Prerequisites: `bash`, `uv`, `ffmpeg` and `ffprobe` on your PATH. The bootstrap
creates a Python 3.12 environment; model weights are downloaded on first use.
See [setup](./references/setup.md) for dependencies and optional backend installation.
For the pyannote path, the assistant guides you through accepting the model terms
and storing a HuggingFace read token. Installed Nemotron needs no token.
The optional [native-backend setup](./references/local-backends.md#reproduce-this-installation)
enables Nemotron diarization for all languages; the [Russian bundle setup](./references/setup.md#one-time-setup-1)
enables GigaAM v3 RNNT. Both are reused on later runs.

> *Why HuggingFace?* It's the open-source equivalent of an app store for AI models. The speaker-recognition model is free, but its authors require accepting a usage agreement once — pretty standard for research-grade open source.

### Don't use Claude Code? Use it with anything else

The core of `scriba` is a bash + Python pipeline. The "skill" layer is a thin wrapper that helps an AI agent guide you through setup and speaker naming — and there's a tool-agnostic version of those instructions in [`AGENTS.md`](./AGENTS.md), supported by most modern AI coding tools.

| Your tool | Installation / instructions | Invocation |
|---|---|---|
| **Claude Code, local session** | `~/.claude/skills/scriba/` as above | `/scriba <file>` |
| **Codex, local session** | Clone into `~/.agents/skills/scriba/`, or link that directory to your existing checkout | Ask to use Scriba with the media path |
| **Other local agents (Cursor, Aider, Goose, etc.)** | Clone anywhere; ask the agent to read the checkout's `SKILL.md` and `AGENTS.md`. It needs file and shell access | Natural-language request with an absolute media path |
| **Browser-only chat without local tools** | Cannot run the local pipeline from a file path alone; run the CLI locally, then provide the resulting transcript | Discuss the finished transcript |
| **No AI agent** | Clone anywhere | `bash <scriba>/scripts/transcribe.sh <file>` |

Official skill locations: [Claude Code](https://code.claude.com/docs/en/skills#where-skills-live),
[Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills).
`AGENTS.md` contains Scriba's agent instructions; it does not grant access to your
computer or make a browser-only chat execute local commands.

## Usage

Easiest path is Claude Code (other agents & the plain CLI: see [Use it with anything else](#dont-use-claude-code-use-it-with-anything-else) above). Open Claude Code, type:

```
/scriba /path/to/your-meeting.mp4
```

Now you can walk away. The assistant runs the transcription in the background. While it's working:

- **Optional statusline**: after [one-time configuration](./references/statusline-integration.md), it shows a line such as `🎙 tx 47% · ETA 01:18`. Its refresh rate depends on your statusline.
- **A macOS notification** signals completion of the local pipeline, before any host-AI punctuation step (`NOTIFY=0` disables it).
- **`--watch <file>`** attaches to a transcription already running, in a side terminal; it does not start a new transcription.

<p align="center">
  <img src="docs/scriba-screen.png" alt="scriba live progress in Claude Code's Shell details" width="900">
</p>
<p align="center"><sub>Example from an earlier run. Shell output contains progress snapshots; whether an inspector refreshes them depends on the client. Use the configured statusline or <code>--watch</code> for live monitoring.</sub></p>

When it finishes, the assistant adds validated punctuation to punctuation-free
output and opens the reading version, preserving the raw files. It also shows
you the speakers it found. For each one you get:

- A **voice clip up to 10 seconds**, embedded in the Markdown and available as a WAV file.
- **Up to three sample utterances** with timestamps.

The assistant asks "who is who?" — you answer (e.g. "Speaker 1 is Alice, Speaker 2 is Bob") — it renames the Markdown labels. When a punctuated copy exists, the same mapping is applied to both Markdown files. JSON labels remain unchanged.

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

The Markdown points at `data/…` with **relative** paths, so the folder travels as a unit. Audio playback requires a viewer that permits HTML audio and local media. GitHub preview may sanitize the player; open the WAV directly if your viewer blocks it.

The **folder/file name is meaningful**: it's derived from your video's name (kebab-cased). When the source name is generic (`zoom_0`, `GMT20260605-120000`, `recording`, …), the assistant picks a real title for you. The original filename is always preserved in the `source:` frontmatter field.

Alongside your recordings, a hidden **`.scriba/`** folder holds corpus-wide state your AI uses to navigate everything: `index.json` (one entry per recording — read once, find any meeting), plus the glossary and persistent voiceprints. Full layout in [`references/file-layout.md`](./references/file-layout.md).

## Beyond one-off meetings — run it automatically

A local watcher can invoke the CLI once per **completed recording**:

```bash
bash ~/.claude/skills/scriba/scripts/transcribe.sh "/path/to/finished-meeting.mp4" --out-dir "/path/to/transcripts"
```

Configure the watcher to wait until recording is complete and avoid duplicate
runs for repeated file-change events. Scriba does not include a watcher or a
persistent processing queue. CLI-only runs produce raw output; host-AI punctuation
is a separate step. Keep the portable output folder together when indexing or
syncing it to your notes/search system.

## Limitations

- Two speakers who sound similar (e.g. brothers, or two soft-spoken voices) may be merged into one.
- Heavy background music or three+ people speaking simultaneously degrades speaker boundaries.
- Tested here on macOS / Apple M4 Max / 36 GB RAM. Other chips, Intel Macs and Linux were not benchmarked or end-to-end validated in these checks. MLX requires Apple Silicon; the default bootstrap includes its extra dependencies.
- First use may download Python packages, runtimes and model weights. Size and initialization time depend on the selected profile and existing caches.
- Diarization routing is shared across languages. A real Russian call and synthetic English/German dialogues were checked; quality has not been measured against human speaker labels across all languages.
- Nemotron handles at most eight speakers. Use `--diarizer pyannote` for larger groups, `--speakers N`, or known-voice enrollment.
- Host-AI punctuation takes extra chat time/tokens and can affect interpretation. It does not repair ASR spelling or speaker errors, and is absent from unattended CLI-only runs.

---

## Advanced — for power users

Use these options to select backends, preserve a comparison profile, and inspect progress.

See [local backend notes](./references/local-backends.md) for model installation
and limits, and [Performance](#performance--how-long-will-it-take) for measured
processing times. Host-AI punctuation is [validated separately](./references/punctuation.md);
keep `--accurate` available when reviewing ASR completeness or spelling.

### Run the bash directly

From the checkout root (or use the full installed script path):

```bash
bash scripts/transcribe.sh "/path/to/meeting.mp4" --lang ru
```

| Flag | Meaning |
|---|---|
| (default) | `--lang ru` with the installed ONNX bundle and no glossary/model override: GigaAM v3 RNNT. Otherwise WhisperX turbo on Apple Silicon, full large-v3 elsewhere. For every language, installed Nemotron is preferred; pyannote is the fallback. |
| `--fast` | Experimental MLX/native timing; review phrase completeness on Russian audio. |
| `--accurate` | Full large-v3 with the original WhisperX decoder and forced alignment. |
| `--asr auto/whisperx/gigaam/gigaam3/mlx/nemotron35` | Choose automatic routing or a specific ASR backend. GigaAM RNNT and GigaAM3 E2E CTC are Russian-only. MLX is experimental. `nemotron35` is opt-in [NVIDIA Nemotron 3.5 Transcribe](./references/local-backends.md#opt-in-nemotron-35-transcribe) for non-Russian / mixed meetings: punctuation, word times and speakers in one pass; needs ~20 GB RAM, 21 GB weights and a NeMo-Speech.cpp nightly; at most one hour per file. |
| `--device cpu/cuda/auto` | WhisperX ASR and alignment device. Default: `cpu`; `auto` picks `cuda` when torch sees a GPU. MLX ignores it. Untested on Linux/CUDA. |
| `--diar-device auto/cpu/mps/cuda` | Set the diarization device separately from ASR. Nemotron maps `mps` to Metal. |
| `--alignment forced/native` | Choose forced alignment or native word times for MLX. |
| `--diarizer auto/pyannote/nemotron` | Explicit local diarizer selection. Nemotron supports up to eight voices; enrollment/count hints use pyannote. |
| `--speakers N` | Set the speaker count through pyannote; automatic selection uses pyannote for this option. Default: auto. |
| `--enroll "Name=clip.wav,..."` | Match known voices through pyannote; matched labels are stored in JSON. Markdown uses anonymous display labels until renamed. |
| `--lang XX` | Force ISO language code (`en`, `ru`, `de`, …). Default: auto-detect. |
| `--model M` | Override the Whisper/GigaAM3 model, or the Nemotron 3.5 decoder GGUF path. Explicit model overrides select WhisperX unless an ASR mode is selected with `--asr`, `--fast` or `--accurate`. |
| `--out-dir DIR` | Output directory; default: alongside the input. |
| `--title "Name"` / `--name "Name"` | Set a meaningful output stem/title. |
| `--bootstrap` | Create/repair the runtime environment; model weights are loaded on first transcription. |
| `--status <file>` | Print a one-line progress summary (cheap to poll). |
| `--watch <file>` | Full-screen TUI watcher (run in a side terminal). |

Speaker renaming after the fact (repeat for `.punctuated.md` if present; this edits Markdown only):

```bash
python3 scripts/rename_speakers.py meeting.transcript/meeting.md "Alice,Bob,Carol"
# or explicit mapping:
python3 scripts/rename_speakers.py meeting.transcript/meeting.md --map "Speaker 1=Alice,Speaker 2=Bob"
```

### Monitoring surfaces

Pick the channel that fits your workflow. The statusline, watcher and status summary use `*.transcript.progress.json` next to the input. The raw log contains backend output; the notification announces successful local completion. Progress and log files are auto-deleted on successful completion, leaving the human-facing `<title>.transcript/` folder. Diagnostic files are kept when something fails.

| Surface | What you do | What you see |
|---|---|---|
| **Statusline integration** | Wire `scripts/statusline.sh` into your Claude Code / tmux / Starship / p10k statusline once. Recipes: [`references/statusline-integration.md`](./references/statusline-integration.md). | `🎙 tx 47%* · ETA 01:18` → `🎙 dia/embedd 50%* · 02:17` → empty. Refresh depends on the configured statusline. No AI polling is needed; pyannote reports sub-step percentages, Nemotron reports its overall stage. |
| **`--watch` TUI** | `bash scripts/transcribe.sh --watch /path/to/file.mp4` in a side terminal. | Attach to an already-running job: progress bar, audio %, ETA, last log line. 2 s refresh. Ctrl-C detaches; transcription keeps running. |
| **`--status` one-liner** | `bash scripts/transcribe.sh --status /path/to/file.mp4` | One line: `stage=transcribe · elapsed 02:30 · ETA 01:18 (observed) · audio 47% (measured) · wall 51% · …` |
| **`*.transcript.progress.json`** | Read the file directly. | Small JSON with the canonical schema (see [`references/eta-factors.md`](./references/eta-factors.md)). Refreshed every 5 s. |
| **macOS notification** | Nothing — fires automatically on `done` if `osascript` is available. | Notification Center card "scriba · <file> · <wall-clock>" with the Glass sound. |
| **`*.transcript.log`** | `tail -f /path/to/file.transcript.log` | Selected-backend output, including `Transcript: […]` when available; pyannote adds `diarize/<step>` counters. Nemotron has no equivalent sub-step percentages. |

### Performance — how long will it take?

Speed depends on the **whole profile**, not just your chip. These are single-run
measurements from October 3, 2026, on **Apple M4 Max, 14 CPU cores, 36 GB RAM**.
The comparison uses the same five-minute Russian group-call excerpt
(Oscar, 31:00–36:00), 16 kHz mono audio, with weights downloaded before timing.

| Profile | Processing time for 5 min audio | Time / audio ratio | Observation |
|---|---:|---:|---|
| Original WhisperX large-v3 CPU + pyannote CPU | 416.8 s (6 min 57 s) | 1.389× | Original comparison profile |
| **GigaAM v3 RNNT int8 CPU + Nemotron 3** | **31.3 s** | **0.104×** | Current Russian route when installed; raw ASR has no punctuation |
| GigaAM v3 E2E CTC MPS + Nemotron 3 | 55.9 s | 0.186× | Optional Russian model; different recognition output |
| Full Whisper large-v3 MLX + Nemotron 3 | 59.7 s | 0.199× | Experimental: omitted phrases on this excerpt |

RNNT was **13.3× faster than the original profile on this excerpt**. A later
RNNT integration rerun took 22.7 s; it is a separate repeat, not the denominator
of that comparison. Lower ratios mean faster processing; `1.0×` means real time.

These times include ASR, alignment when needed, diarization and initialization
inside the Python wrapper. They **exclude** media extraction, Markdown/voice-clip
rendering and host-AI punctuation. Model downloads and first-use Metal compilation
can add time. No one-hour run or other-chip speed prediction is established by
this five-minute test. The old M1–M4 estimates are retained only as legacy ETA
heuristics in [ETA notes](./references/eta-factors.md), not as current benchmarks.

Separate multilingual integration checks:

| Input | Language selection | Profile | Audio / processing time | Check |
|---|---|---|---|---|
| Synthetic English, two local voices | `--lang en` | WhisperX turbo CPU + Nemotron | 52.2 s / 51.6 s | Two voice labels retained across six turns |
| Synthetic German, two local voices | auto-detected `de` | WhisperX turbo CPU + Nemotron | 67.8 s / 62.5 s | Two voice labels retained across six turns |

These short synthetic checks verify routing and speaker continuity, not
accuracy on real calls or relative language performance. The separate Russian
WhisperX turbo run overlapped another process and is excluded from the speed
comparison. There is no human-checked transcript/RTTM here, so these results do
not establish equal WER/DER across models or languages.

[Machine-readable measurements](./benchmarks/local-performance-2026-10-03.json)
and [backend notes](./references/local-backends.md) record the scope and limits.

**ETA:** the script learns a separate calibration factor for each ASR/model,
diarizer, diarization device and alignment profile at
`~/.config/scriba/calibration.json`. Eligible runs have at least 60 s of audio
and more than 10 s of recorded processing. Before calibration, legacy chip
heuristics can substantially overestimate a new fast profile. Live audio progress
uses segment timestamps where available; alignment and diarization have no
reliable completion ETA. `100%` of audio decoded is not the finished transcript.
The macOS completion notification and script timing cover the local pipeline;
AI punctuation takes additional session time/tokens.

To contribute measurements, include the exact profile and timing scope rather
than extrapolating another chip's results: [contribution guide](./CONTRIBUTING.md).

### How it works

1. `transcribe.sh` extracts the input to 16 kHz mono WAV via ffmpeg.
2. `transcribe_whisperx.py` runs the selected ASR backend (GigaAM, WhisperX, or experimental MLX). It retains word timing where available (alignment can fail) and emits segment progress where supported.
3. The shared resolver selects Nemotron or pyannote independently of language. Nemotron runs through the local native CLI; pyannote runs with `TextProgressHook` so its sub-steps report real `completed/total` counters. Both feed word-level speaker assignment, short-turn reconciliation and uncertainty flags.
4. A bash ticker scans the log every 5 s and writes the canonical `*.progress.json`.
5. The statusline, watcher and status summary read that progress JSON; the raw log remains available during processing.
6. On exit, `json_to_md.py` turns the JSON into Markdown inside `<title>.transcript/`, ffmpeg cuts one ≤10 s WAV clip per speaker into its `data/` folder for the embedded `<audio>` players, the JSON sidecar is copied there too, and `update_index.py` upserts the recording into `.scriba/index.json`. See [`references/file-layout.md`](./references/file-layout.md).
7. When an AI is driving the skill, it can restore punctuation through `punctuate.py` and render a separate reading version using the existing clips. This step is outside the local pipeline and its ETA.

## License

[MIT](./LICENSE) — © 2026 [Alexander Abramov](https://github.com/AlexanderAbramovPav).
Source & issues: <https://github.com/AlexanderAbramovPav/scriba>

Runtime dependencies and model weights (WhisperX, pyannote, GigaAM, Nemotron, optional MLX, and ffmpeg) are installed separately, not vendored. Their licenses are catalogued in [`THIRD_PARTY_LICENSES.md`](./THIRD_PARTY_LICENSES.md).

Dependencies and model weights have their own licenses, including CC-BY-4.0
for pyannote community-1 and OpenMDW 1.1 for Nemotron 3. Consult the upstream
license links in [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) for your
use and redistribution; Scriba's MIT license does not replace those terms.

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
