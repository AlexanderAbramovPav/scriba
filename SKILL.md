---
name: scriba
description: Transcribe any audio/video meeting into an accurate, speaker-diarized Markdown transcript (Speaker 1/2/3), then rename speakers to real names. Use when the user drops an audio or video file and wants a transcript, расшифровку, транскрипт, диаризацию, "кто что сказал", or asks to транскрибировать/расшифровать встречу или запись.
---

# scriba

Turns any audio/video file into an accurate, speaker-diarized Markdown transcript. Two-pass:
first produce `Speaker 1/2/3` + representative samples, then rename to real people.

## First-run setup — the AI handles it; the user only clicks 3 links and pastes a token

**Before you call `transcribe.sh` for the first time on this machine, check whether `~/.config/scriba/hf_token` exists.** If it does, skip this block. If it doesn't, the user needs a HuggingFace token *before* diarization can work — and they should NOT be left to figure that out alone. Walk them through it conversationally in their language (the chat's language is the user's language; default to English when ambiguous). The flow:

> «Чтобы определить, кто что говорит, нужен бесплатный HuggingFace-токен (~30 секунд):
>
> 1. Открой <https://huggingface.co/join> — заведи аккаунт, если нет.
> 2. Открой <https://huggingface.co/pyannote/segmentation-3.0> и нажми «Agree and access repository» (один клик).
> 3. То же на <https://huggingface.co/pyannote/speaker-diarization-community-1> — это модель, которая распознаёт спикеров (один клик).
> 4. Открой <https://hf.co/settings/tokens> → «+ Create new token» → имя `scriba`, тип **Read**, скопируй сгенерированный токен (вид `hf_...`).
> 5. Вставь его сюда в чат — я сохраню локально с правами 600 и больше никогда не попрошу.»

When the user pastes the token, write it via Bash:
```
mkdir -p ~/.config/scriba && umask 077 && printf '%s\n' '<TOKEN>' > ~/.config/scriba/hf_token && chmod 600 ~/.config/scriba/hf_token
```

Then continue with the transcription. Tell the user the token is read-only and can be revoked at any time from `https://hf.co/settings/tokens`.

**Without the token transcription still works**, you just get one collapsed `Speaker 1` for everyone. If the user explicitly says they don't want to set up HF, proceed without the token — but warn them once that speakers won't be separated.

**Prereqs check.** Before transcribing, also verify `bash`, Python 3.10+, `uv`, and `ffmpeg`/`ffprobe` are on `$PATH`. If any are missing, name the missing tool to the user and give them the exact install command for their OS (`brew install ffmpeg` on macOS, `curl -LsSf https://astral.sh/uv/install.sh | sh` for uv on either OS, etc.). Don't try to install for them — just tell them what to run.

First invocation of `transcribe.sh` auto-bootstraps `.venv` and downloads model weights (~5 min, ~3 GB). Subsequent runs reuse the cache and start in seconds.

## Modes
- **Default = accuracy:** whisperX large-v3 on CPU + pyannote `community-1`. Strong "who said
  what" — `community-1`'s authors report ~10–11% DER on standard benchmarks, and the model is
  chosen to run on a normal Mac, not only a top-end one. Don't claim a scriba-specific accuracy
  number you haven't measured; the user can measure DER on their own labeled audio with
  `scripts/benchmark_der.py` (see `benchmarks/`). Slower — a ~1 h meeting ≈ 1–2 h of compute.
  **Run long files in the background** (e.g. via a background shell).
- **`--fast`:** MLX (GPU) transcription, coarser speaker boundaries. Use when speed matters.

## Workflow

### Pass 1 — transcribe
Run (background for long files; **don't pipe to `tail -N`** — it buffers until EOF and hides progress):
```
bash skills/scriba/scripts/transcribe.sh "<media-file>" [--fast] [--speakers N] [--lang XX]
```
This writes the transcript into a portable folder `<title>.transcript/` next to the input
(`<title>.md` + a `data/` subfolder with the JSON sidecar and per-speaker voice clips) and
prints the folder path. `<title>` is the input filename kebab-cased; when the filename is
generic (`zoom_0`, `GMT…`, `recording`, a bare date), pass `--title "<meaningful name>"` and
it's used instead. To decide, you can check the filename with
`python3 skills/scriba/scripts/naming.py generic "<input-stem>"` (prints `1` if generic).
It also prints a banner with the wall-clock ETA and the paths of two
live-status files (see "Monitoring" below). Full layout: `references/file-layout.md`.

#### Glossary biasing (mixed RU/EN terminology)

Domain terms get mangled by ASR — product names, people, acronyms, and English tech words spoken
inside Russian. Bias the model toward the right spellings: assemble these terms from the meeting's
context (invite, agenda, prior transcripts in the same folder) and write them **one per line** to
`<recordings-dir>/.scriba/glossary.txt` (next to the media). Blank lines and `#` comments are
ignored. They feed `initial_prompt`/`hotwords` and bias **every** run in that folder. A global
fallback list lives at `~/.config/scriba/glossary` (project terms take precedence). Maintaining
correct spellings here is the cheapest lever for mixed-terminology accuracy.

#### Known-speaker enrollment (skip "who is Speaker N?")

If you have a short single-speaker reference clip per known person, pass them so their speakers
come out **pre-named by construction** instead of `Speaker N`:
```
bash skills/scriba/scripts/transcribe.sh "<media-file>" --enroll "Alice=alice.wav,Bob=bob.wav"
```
Matching uses community-1 voice embeddings + a cosine threshold: each meeting cluster is matched
to its best reference above threshold (greedy, so a name claims at most one cluster). **Unmatched
speakers stay `Speaker N`** and go through the normal identify/rename flow. For matched speakers,
skip the "who is Speaker N?" question.

**Persistent voiceprints vs per-recording clips.** Reusable reference clips ("voiceprints") live
in `.scriba/voiceprints/` (project, next to the media) over `~/.config/scriba/voiceprints/`
(global), and feed `--enroll` across meetings. These are distinct from the per-recording listening
clips embedded at `<title>.transcript/data/speaker-N.wav` (those are just for this one meeting's
ID). After the user names a new speaker, you may offer to save a reference clip as a voiceprint so
that person is auto-recognised in future meetings.

### Monitoring a running transcription

**Default UX — point the user at the external surfaces, don't poll from the AI side.** Status visibility is free this way (zero AI tokens) and works whether the user keeps the chat open or not:

- **In the Claude Code chat's own statusline** (preferred — same window, no extra terminal needed). The skill ships `scripts/statusline.sh`, which prints `🎙 <stage> <pct>%* · ETA MM:SS` while a transcription runs (`*` = real, from a whisperX `Transcript: [...]` line; `~` = extrapolated, used in warmup / MLX path) and **stays silent** otherwise. To make it show up in the chat's bottom strip the user has to wire the script into their statusline once — recipes for claude-hud, the vanilla Claude Code `statusLine`, tmux, Starship, p10k, fish/zsh are in `references/statusline-integration.md`. The skill itself does not edit anyone's settings, so this is opt-in; mention it to the user the first time, point them at the file, and don't re-pitch. If they've already wired it but see nothing, the most common cause is they haven't restarted the Claude Code session since editing `settings.json`.
- **For passive use** (launch and walk away): macOS Notification Center pings the user automatically when `stage=done` (Glass sound, with the output path). Tell the user: «нотификация прилетит, когда готово».
- **For active watching**: `bash <skill>/scripts/transcribe.sh --watch "<media-file>"` — full-screen TUI in a side terminal: progress bar, audio %, ETA, last log line, refreshes every 2 s. Detach with Ctrl-C, transcription keeps running. Zero AI tokens.
- **For a quick poke**: `tail -f "<input-stem>.transcript.log"` — raw whisperX output streaming, including each `Transcript: [start --> end] text` segment as it lands.

Tell the user these options when you launch. **Do NOT routinely poll from inside the chat** — every Monitor event or `--status` call costs AI tokens, and over a long run the cache misses add up fast.

When AI-side polling **is** appropriate (the user explicitly asks "как там?", or you need to gate on completion before moving to the speakers step):
- One-shot: `bash <skill>/scripts/transcribe.sh --status "<media-file>"` → single line `stage · elapsed · ETA (src) · audio % (src) · wall % · last_log`. Cheap.
- Streaming, very long run: spawn ONE `Monitor` that emits only on **stage changes** and **25 %** audio boundaries — not 10 %, not on every tick. That keeps event count ≤ 6–8 for a typical meeting.

**Never** use `/loop`, `ScheduleWakeup`, or any periodic wake-up to check on the transcription — every wake-up is a guaranteed prompt-cache miss (~10 K tokens) and adds up to dollars over a long run with no benefit you don't get from the silent macOS notification.

#### Schema for `<stem>.transcript.progress.json` (small, ~350 B, refreshed every 5 s)

| Field                  | Meaning |
| ---------------------- | ------- |
| `stage`                | `init` / `extract` / `transcribe` / `align` / `diarize` / `finalize` / `done`. The ticker refines whisperX's super-stage into `align` and `diarize` sub-stages by scraping log markers. |
| `stage_sec`            | elapsed wall-clock inside the current stage (resets on each transition). |
| `elapsed_sec`, `audio_sec`, `warmup_sec` | wall-clock since start, audio length, observed model-load overhead |
| `audio_processed_sec` · `audio_processed_pct` · `audio_source` | position inside the audio; `audio_source` is `measured` (whisperX emitted at least one `Transcript: [...]`) or `extrapolated` (factor × elapsed; MLX path or pre-first-segment). Only meaningful during `transcribe`; after `align`/`diarize` start, audio is already 100 % processed. |
| `eta_total_sec` · `eta_remaining_sec` · `pct` · `eta_source` | best ETA for the **transcribe** stage; align/diarize are unpredictable and have no live ETA — show `stage_sec` instead. `eta_source`: `observed` (real audio rate) · `calibrated` (cache) · `chip_default` · `fallback` |
| `factor`, `chip`, `started_at`, `last_log` | metadata + latest live log line |

During `align` and `diarize` whisperX is silent for tens of seconds. The wrapper emits `→ <step>… (Ns)` heartbeats every 10 s to keep the log visibly alive — that's how you can tell pyannote hasn't hung. The statusline (`scripts/statusline.sh`) shows `🎙 align · 00:25` / `🎙 diarize · 00:35` with the in-stage timer for the same reason.

Full ETA model and chip table in `references/eta-factors.md`.

**Note on Claude Code's "Shell details" view**: that inspector shows a snapshot of the bash task — runtime and output don't auto-refresh. For live status, point the user at the **statusline** (3 s refresh) or `--watch` TUI (2 s refresh). Re-opening "Shell details" pulls a fresh snapshot.

### Identify speakers
Open the transcript and read the `## Speakers — identify who's who` section to the user
in their chat language (translate the headings on the fly if the user chats in Russian/etc;
the section is always written in English in the file). For each `Speaker N` show: the
talk-time %, **the path to the embedded `data/speaker-N.wav` clip** (so
they can listen if the text quote isn't enough), and the three textual samples. Ask who
each speaker is and wait for their mapping (e.g. "Speaker 1 = Alice, Speaker 2 = Bob"). The
audio clip is the most reliable ID signal — point at it explicitly for users who don't
recognise the voice from text alone.

### Pass 2 — rename
```
python3 skills/scriba/scripts/rename_speakers.py "<title>.transcript/<title>.md" "Иван,Аня"
# or explicit:
python3 skills/scriba/scripts/rename_speakers.py "<title>.transcript/<title>.md" --map "Speaker 1=Иван,Speaker 2=Аня"
```

## Rules
- **Always run the first-run setup check above before invoking `transcribe.sh`** on a new machine. Don't skip it and don't fail silently to diarization-less mode — the user will be confused why everyone is "Speaker 1". Walk them through the HF-token onboarding the first time only; the file's presence is the cue to skip on later runs.
- **Match the user's language** in conversation (Russian / English / etc. — whatever they chat in). The transcript text itself stays verbatim in whatever language the audio was in.
- Never invent speaker names — always get them from the user via the samples (text quote *and* embedded `<audio>` clip).
- For long inputs, launch pass 1 in a background shell and tell the user it's running; don't block.
- **After launching, tell the user about the external UI surfaces** — the macOS notification (fires on `done`) and the `--watch` TUI command — so they can see progress without burning AI tokens. One short line is enough, in their language. Example (RU): «Запустил. Нотификация прилетит на готовности; для живой картинки — `bash <skill>/scripts/transcribe.sh --watch "<file>"` в соседнем терминале.»
- After that **wait silently** for the bg task to complete — do not periodically poll `--status` and do not spawn long-running Monitors unless the user explicitly asks for in-chat updates. The bg task notification fires when it's done; that's your cue to read the transcript.
- If the user explicitly asks for in-chat progress, prefer ONE `Monitor` over `<stem>.transcript.progress.json` with a **25 %** audio threshold and stage-change emissions — not 10 %, not every tick. Stop the Monitor once you see `stage=done`.
- **Never** use `/loop`, `ScheduleWakeup`, or any timed wake-up to poll the transcription — every wake-up is a prompt-cache miss (~10 K tokens) and provides nothing you don't already get for free from the macOS notification.
- Do NOT read the bg-task stdout file or the `.transcript.log` for status — they're verbose. The cheap channels are `--status` (one line) and `*.progress.json` (small object).
- When presenting speakers for naming, show both the text samples AND the embedded `<audio>` clip path — the audio is the real ID signal for non-technical users.
