# AGENTS.md — instructions for AI assistants driving scriba

This file is the tool-agnostic counterpart to `SKILL.md` (which is Claude Code–specific). If you're an AI agent running inside Codex CLI, Cursor, Continue, Aider, Goose, JetBrains AI, or any other coding/chat tool, and the user has asked you to help with a meeting transcription — read this.

## What scriba is

`scriba` is a local, MIT-licensed tool that turns any audio/video file into a speaker-diarized Markdown transcript with embedded audio clips of each speaker. The CLI entry point is:

```bash
bash <scriba>/scripts/transcribe.sh <media-file>
```

Where `<scriba>` is wherever this repo was cloned. Typical paths:
- `~/.claude/skills/scriba/` (Claude Code convention — still works for any tool)
- `~/.config/scriba/` or `~/dev/scriba/` (standalone install)
- A relative path inside a project that vendors it

No AI is required to run scriba — the pipeline is just bash + Python. Your role as an agent is to make the experience pleasant: handle the first-run setup, surface live status without spamming, and help the user name speakers when it's done.

## First-run setup — handle it for the user

Before invoking `transcribe.sh` the first time on a machine, check whether `~/.config/scriba/hf_token` exists. If it does, skip this. If it doesn't, do **not** silently fall through to diarization-less mode — the user will be confused why everyone is `Speaker 1`.

Walk them through the HuggingFace onboarding conversationally, in their language (English by default, match the user's chat language otherwise):

> To identify who's speaking, scriba needs a free HuggingFace token (~30 seconds):
>
> 1. Open <https://huggingface.co/join> — create a free account if you don't have one.
> 2. Open <https://huggingface.co/pyannote/segmentation-3.0> and click "Agree and access repository" (one click).
> 3. Same on <https://huggingface.co/pyannote/speaker-diarization-community-1> — the model that identifies speakers (one click).
> 4. Open <https://hf.co/settings/tokens> → "+ Create new token" → name it `scriba`, type **Read**, copy the generated token (looks like `hf_...`).
> 5. Paste it here in the chat — I'll save it locally with `chmod 600` and never ask again.

When the user pastes the token, save it with a shell command:

```bash
mkdir -p ~/.config/scriba && umask 077 && printf '%s\n' '<TOKEN>' > ~/.config/scriba/hf_token && chmod 600 ~/.config/scriba/hf_token
```

The token is read-only and revocable any time at <https://hf.co/settings/tokens>. Tell the user that.

**Without the token** transcription still works, you just get one collapsed `Speaker 1` for everyone. If the user explicitly says they don't want HuggingFace, proceed without — but warn once that speakers won't be separated.

## Prerequisite check

Verify `bash`, Python 3.10+, `uv`, and `ffmpeg`/`ffprobe` are on `$PATH`. If any are missing, name the missing tool and give the exact install command for their OS (`brew install ffmpeg` on macOS, `curl -LsSf https://astral.sh/uv/install.sh | sh` for uv on either OS, etc.). Don't try to install for them — just tell them what to run.

The first invocation of `transcribe.sh` auto-bootstraps the `.venv` and downloads model weights (~5 min, ~3 GB). Subsequent runs reuse the cache.

## Running a transcription

For a long file (anything over ~30 s of audio), launch in the background — the pipeline runs minutes-to-hours depending on length and chip. Concrete command pattern depends on your tool, but the intent is "spawn the process detached, don't block the chat":

```bash
nohup bash <scriba>/scripts/transcribe.sh "<media-file>" > /tmp/scriba.log 2>&1 & disown
```

Then **tell the user about the external status surfaces** (see below) — one short line — and **wait silently** for the bg process to complete. Do not periodically poll status. The macOS notification (on completion) is your cue to read the output.

## Glossary biasing — assemble domain terms for mixed-terminology accuracy

ASR mangles product names, people, acronyms, and English tech terms spoken inside another language. Bias the model toward correct spellings: gather these terms from the meeting's context (invite, agenda, prior transcripts in the same folder) and write them **one per line** to `<recordings-dir>/.scriba/glossary.txt` (next to the media). Blank lines and `#` comments are ignored. They feed `initial_prompt`/`hotwords` and bias **every** run in that folder. A global fallback list lives at `~/.config/scriba/glossary` (project terms take precedence). Keeping this list accurate is the cheapest lever for mixed RU/EN terminology.

## Known-speaker enrollment — pre-name speakers you already have voiceprints for

When you have a short single-speaker reference clip per known person, pass `--enroll "Alice=alice.wav,Bob=bob.wav"` to `transcribe.sh`. Matched speakers come out **pre-named by construction** (real names baked into segments and words), so you can **skip the "who is Speaker N?" question for them**. Matching uses community-1 voice embeddings + a cosine threshold (greedy: each reference claims at most one cluster). **Unmatched speakers stay `Speaker N`** and follow the normal identify/rename flow below.

Distinguish two clip kinds: **persistent voiceprints** in `.scriba/voiceprints/` (project, at the recordings root) over `~/.config/scriba/voiceprints/` (global) are reusable references fed to `--enroll` across meetings; the per-recording `<title>.transcript/data/speaker-N.wav` listening clips are just this one meeting's ID samples. After the user names a new speaker, you may offer to save a reference clip as a voiceprint so they're auto-recognised next time.

## Monitoring surfaces — point the user at these, don't burn tokens polling

`scriba` writes live-status files next to the input (keyed to the **raw input stem**) while running, and the final output into a per-recording folder (see "Output layout" below):

- `<input-stem>.transcript.progress.json` — small (~350 B) machine-readable state, refreshed every 5 s while running. **Auto-deleted on successful completion** (kept only on failure). To gate on completion, call `--status` (it reports `stage=done · transcript: <path>` once progress.json is gone but the transcript exists) rather than guessing the output path.
- `<input-stem>.transcript.log` — raw whisperX + pyannote output. Verbose, do not read in full. **Auto-deleted on success**; preserved for post-mortem when something fails.

**Output layout (kept).** The final transcript is a portable folder `<title>.transcript/` containing `<title>.md` plus a `data/` subfolder with the JSON sidecar (`data/transcript.json`) and one ≤10 s WAV per speaker (`data/speaker-N.wav`). `<title>` is the meaningful output stem (the input filename kebab-cased, or the `--title` you pass when the filename is generic). To decide whether a name is generic, check it with `python3 <scriba>/scripts/naming.py generic "<input-stem>"` (prints `1` if generic). `transcribe.sh` prints the folder path on success. A hidden `.scriba/index.json` at the recordings root is upserted with one entry per recording so you can find any meeting from a single file. Full layout: `references/file-layout.md`.

Plus three external surfaces for the human:

- **Statusline integration** — `bash <scriba>/scripts/statusline.sh` outputs one line like `🎙 dia/embedd 50%* · 02:17` when active, silent otherwise. The user wires this into their tmux / Starship / p10k / fish / claude-hud once. Recipes in `references/statusline-integration.md`.
- **`--watch` TUI** — `bash <scriba>/scripts/transcribe.sh --watch "<media-file>"` in a side terminal renders a full-screen progress bar. Detach with Ctrl-C; transcription keeps running.
- **macOS notification** — fires automatically on `stage=done` (Glass sound, output path in the body).

When the user asks "how's it going?", run `bash <scriba>/scripts/transcribe.sh --status "<media-file>"` — that returns one line, cheap. Don't tail the log; don't read the bg-task stdout file; don't spawn periodic polling loops.

## When transcription finishes — help the user name the speakers

Read the resulting `<title>.transcript/<title>.md`. After the H1 title it opens with a `## Speakers — identify who's who` section: for each `Speaker N` the file gives a talk-time %, an embedded `<audio>` clip path under `data/speaker-N.wav`, and three textual sample utterances.

Surface this to the user in their chat language (translate the headings if needed; the file itself stays English). The audio clip is the most reliable identification signal — explicitly point at it for users who don't recognise the voice from text alone.

Wait for the mapping (e.g. "Speaker 1 = Alice, Speaker 2 = Bob"), then run:

```bash
python3 <scriba>/scripts/rename_speakers.py "<title>.transcript/<title>.md" "Alice,Bob,Carol"
```

(Comma-separated, in the order `Speaker 1, 2, 3, …`. Or use the explicit form: `--map "Speaker 1=Alice,Speaker 2=Bob"`.)

## Rules

- **Always run the first-run setup check above before invoking `transcribe.sh`** on a new machine. Don't skip it and don't fail silently to diarization-less mode.
- **Match the user's language** in conversation. The transcript text itself stays verbatim in whatever language the audio was in.
- **Never invent speaker names** — always get them from the user via the samples (text quote + audio clip).
- **Wait silently** for background transcriptions to finish. The macOS notification is the cue. The user can watch the statusline / TUI on their own; you don't need to narrate progress.
- If the user explicitly asks for progress in-chat, run `--status` once and report the line verbatim. Do not loop; do not set up timed wake-ups.
- **Never** use any timed wake-up mechanism (e.g. cron, scheduled re-invocation, polling loops) to check on the transcription — every wake-up is a full prompt-cache miss and adds up to nothing the silent notification doesn't already give for free.
- Do NOT read the bg-task stdout file or the `.transcript.log` for status — they're verbose. Use `--status` (one line) or `*.progress.json` (small object) instead.
- When presenting speakers for naming, show both the text samples AND the embedded `<audio>` clip path.

## Tool-specific notes

- **Claude Code** — `SKILL.md` is the primary entry; this `AGENTS.md` is redundant for Claude. Slash command: `/scriba <file>`.
- **Codex CLI** (OpenAI) — reads `AGENTS.md` from the project root or `~/.codex/AGENTS.md`. Place this file there.
- **Cursor** — drop a copy in `.cursor/rules/scriba.md` (project) or reference from `.cursorrules`.
- **Continue.dev** — register `bash <scriba>/scripts/transcribe.sh` as a custom slash command in `~/.continue/config.yaml`, then point the agent at this file for context.
- **Aider** — `aider --read <scriba>/AGENTS.md <your-file>` adds this as ambient context.
- **Anything else** — copy-paste this file into the system prompt / instructions field, plus tell the AI where the `scriba` repo lives.

If your tool doesn't support files at all (browser ChatGPT, mobile app, etc.), the bash CLI still works directly — no AI orchestration needed.
