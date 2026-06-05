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

## Monitoring surfaces — point the user at these, don't burn tokens polling

`scriba` writes three files next to the input while running:

- `<stem>.transcript.progress.json` — small (~350 B) machine-readable state, refreshed every 5 s while running. **Auto-deleted on successful completion** (kept only on failure). If you need to gate on completion, check for the existence of `<stem>.transcript.md` itself instead, OR call `--status` (which reports `stage=done · transcript: <path>` when progress.json is gone but the transcript exists).
- `<stem>.transcript.log` — raw whisperX + pyannote output. Verbose, do not read in full. **Auto-deleted on success**; preserved for post-mortem when something fails.
- `<stem>.transcript.media/` — created at the end with one ≤10 s WAV per speaker. Kept.
- `<stem>.transcript.md` — the final Markdown transcript. Kept.

Plus three external surfaces for the human:

- **Statusline integration** — `bash <scriba>/scripts/statusline.sh` outputs one line like `🎙 dia/embedd 50%* · 02:17` when active, silent otherwise. The user wires this into their tmux / Starship / p10k / fish / claude-hud once. Recipes in `references/statusline-integration.md`.
- **`--watch` TUI** — `bash <scriba>/scripts/transcribe.sh --watch "<media-file>"` in a side terminal renders a full-screen progress bar. Detach with Ctrl-C; transcription keeps running.
- **macOS notification** — fires automatically on `stage=done` (Glass sound, output path in the body).

When the user asks "how's it going?", run `bash <scriba>/scripts/transcribe.sh --status "<media-file>"` — that returns one line, cheap. Don't tail the log; don't read the bg-task stdout file; don't spawn periodic polling loops.

## When transcription finishes — help the user name the speakers

Read the resulting `<stem>.transcript.md`. It opens with a `## Speakers — identify who's who` section: for each `Speaker N` the file gives a talk-time %, an embedded `<audio>` clip path under `<stem>.transcript.media/speaker-N.wav`, and three textual sample utterances.

Surface this to the user in their chat language (translate the headings if needed; the file itself stays English). The audio clip is the most reliable identification signal — explicitly point at it for users who don't recognise the voice from text alone.

Wait for the mapping (e.g. "Speaker 1 = Alice, Speaker 2 = Bob"), then run:

```bash
python3 <scriba>/scripts/rename_speakers.py "<stem>.transcript.md" "Alice,Bob,Carol"
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
