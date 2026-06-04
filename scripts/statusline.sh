#!/usr/bin/env bash
# Statusline label for scriba — portable, opt-in.
#
# Designed to be a *fragment* you compose into whatever statusline you already use:
#   - claude-hud  : pass --extra-cmd <this-script> (claude-hud will inline our output)
#   - vanilla Claude Code statusLine: set this script directly (it'll be the whole strip
#                   while a transcription runs, empty otherwise)
#   - Starship / Powerlevel10k / tmux: invoke from a custom segment
#
# Behavior:
#   - prints ONE short line when a transcription is active (stage != done)
#   - prints nothing otherwise (most statuslines will collapse the slot)
#   - never blocks, never errors out loud — bounded by python3 + a single file read
#
# Source of truth: ~/.cache/scriba/active (single text line: absolute path to
# the running progress.json). transcribe.sh writes it on start, removes it on exit.
set -u
ACTIVE="$HOME/.cache/scriba/active"
[[ -f "$ACTIVE" ]] || exit 0

PROG="$(cat "$ACTIVE" 2>/dev/null || true)"
[[ -n "$PROG" && -f "$PROG" ]] || exit 0

python3 - "$PROG" 2>/dev/null <<'PY'
import json, sys
try:
    p = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
stage = p.get('stage', '?')
if stage == 'done':
    sys.exit(0)

def fmt(s):
    s = int(s or 0); m, ss = divmod(s, 60); return f"{m:02d}:{ss:02d}"

# Render is stage-aware: transcribe shows audio % + ETA (we know both from the live
# `Transcript: [...]` lines). For everything else (align/diarize/extract/finalize) we
# don't have a real % or ETA, so we just show stage name + elapsed-in-stage.
stage_sec = fmt(p.get('stage_sec'))

if stage == 'transcribe':
    pct = int(p.get('audio_processed_pct') or 0)
    eta = fmt(p.get('eta_remaining_sec'))
    src_mark = '*' if p.get('audio_source') == 'measured' else '~'
    print(f"🎙 tx {pct}%{src_mark} · ETA {eta}", end="")
elif stage == 'align':
    print(f"🎙 align · {stage_sec}", end="")
elif stage == 'diarize':
    # Prefer the real pyannote sub-step + % from the hook; fall back to stage timer.
    step = p.get('diarize_step') or ''
    step_pct = int(p.get('diarize_step_pct') or 0)
    if step:
        # `seg` / `emb` / `clu` / `dis` are common pyannote step names — shorten if long.
        short = step.replace('_', '')[:6]
        print(f"🎙 dia/{short} {step_pct}%* · {stage_sec}", end="")
    else:
        print(f"🎙 diarize · {stage_sec}", end="")
elif stage == 'extract':
    print(f"🎙 wav · {stage_sec}", end="")
elif stage == 'finalize':
    print(f"🎙 md · {stage_sec}", end="")
elif stage == 'init':
    print(f"🎙 init · {stage_sec}", end="")
else:
    print(f"🎙 {stage[:6]} · {stage_sec}", end="")
PY
