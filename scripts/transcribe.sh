#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$SKILL_DIR/.venv"
PY="$VENV/bin/python"
WHISPLY="$VENV/bin/whisply"
HF_TOKEN_FILE="${HF_TOKEN_FILE:-$HOME/.config/scriba/hf_token}"
CALIB_FILE="${CALIB_FILE:-$HOME/.config/scriba/calibration.json}"
ETA_HELPER="$SKILL_DIR/scripts/eta_helper.py"

bootstrap() {
  if [[ -x "$WHISPLY" ]]; then
    echo "whisply already installed at $WHISPLY" >&2
    return 0
  fi
  command -v uv >/dev/null || { echo "ERROR: uv not found on PATH" >&2; exit 1; }
  echo "Creating venv (Python 3.12) at $VENV ..." >&2
  uv venv --python 3.12 "$VENV"
  echo "Installing whisply[mlx] (pulls torch/pyannote/whisperX; takes a few minutes) ..." >&2
  uv pip install --python "$PY" "whisply[mlx]"
  echo "Bootstrap done. If you hit an OpenMP crash, KMP_DUPLICATE_LIB_OK=TRUE is already set by this script." >&2
}

usage() {
  cat >&2 <<EOF
Usage: transcribe.sh <media-file> [--fast] [--speakers N] [--lang XX] [--model M] [--out-dir DIR] [--title "<name>"]
       transcribe.sh --bootstrap
       transcribe.sh --status <media-file>     # one-line progress (cheap to poll, AI-friendly)
       transcribe.sh --watch  <media-file>     # live TUI in this terminal (humans, no AI tokens)

  default: accuracy mode (whisperX large-v3 on CPU + pyannote diarization)
  --fast        : MLX (GPU) transcription, coarser speaker boundaries
  --speakers N  : hint number of speakers (default: auto)
  --enroll "Name=clip.wav,..." : pre-name speakers matched to known voices
  --lang XX     : force language (default: auto-detect)
  --model M     : whisper model (default: large-v3)
  --asr whisperx|gigaam : ASR backend (default: whisperx). gigaam = Russian-only,
                  opt-in (sherpa-onnx GigaAM-RU, ~-50% WER vs Whisper on RU); requires
                  one-time setup (see references/setup.md). Auto-selected when
                  --lang ru AND env SCRIBA_RU_GIGAAM=1. Ignored on the --fast/MLX path.
  --out-dir DIR : output directory (default: alongside input)
  --title "<name>" : human title for the output folder/file/H1 (use when the source
                  filename is generic, e.g. zoom_0 / GMT20260605-120000 / recording)

Live progress while transcribing (written next to the input):
  <stem>.transcript.progress.json  — machine-readable, refreshed every 5s
  <stem>.transcript.log            — raw whisperX output (tail -f for live view)
  bash transcribe.sh --status <in> — one-line summary (cheap; AI can call this)
  bash transcribe.sh --watch  <in> — full-screen TUI; for humans in a side terminal

On stage=done the script fires a macOS notification (Glass sound) so you can launch and
walk away.

ETA model:  wall_clock ≈ warmup + audio_sec × factor.
  factor is picked from the chip table in scripts/eta_helper.py (see references/eta-factors.md),
  then overridden by $CALIB_FILE after the first observed run.
EOF
  exit 1
}

# ---- --watch: live TUI in this terminal (zero AI tokens, for humans) ----
if [[ "${1:-}" == "--watch" ]]; then
  [[ -n "${2:-}" && -f "${2}" ]] || { echo "Usage: transcribe.sh --watch <media-file>" >&2; exit 1; }
  IN_W="$2"
  STEM_W="$(basename "${IN_W%.*}")"
  PROG_W="$(dirname "$IN_W")/$STEM_W.transcript.progress.json"

  # Wait for the progress file to appear (background run writes it after ~1-3s of init).
  if [[ ! -f "$PROG_W" ]]; then
    echo
    echo "  [scriba --watch]"
    echo "  Waiting for progress file:"
    echo "    $PROG_W"
    echo
    echo "  Run the transcription first:"
    echo "    bash $0 \"$IN_W\""
    echo "  (in another terminal, or in the background of this one with '&' at the end)"
    echo
    echo "  Then re-run --watch, or it will auto-attach once the file appears."
    echo
    printf "  waiting"
    for i in $(seq 1 60); do  # up to 2 min
      [[ -f "$PROG_W" ]] && { echo " ✓"; break; }
      sleep 2
      printf "."
    done
    echo
  fi
  [[ -f "$PROG_W" ]] || { echo "  no progress file after 2 min — is the background run alive?" >&2; exit 1; }

  # Hide cursor, restore on Ctrl-C; the underlying transcription keeps running.
  tput civis 2>/dev/null
  trap 'tput cnorm 2>/dev/null; echo; exit 0' INT TERM EXIT

  while true; do
    rendered=$(python3 - "$PROG_W" "$IN_W" <<'PY'
import json, os, sys
prog_path, in_path = sys.argv[1], sys.argv[2]
try:
    p = json.load(open(prog_path))
except Exception:
    print(f"(reading {prog_path}...)"); print("__BUSY__"); sys.exit(0)

def fmt(s):
    s = int(s or 0); h, r = divmod(s, 3600); m, ss = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{ss:02d}" if h else f"{m:02d}:{ss:02d}"

def bar(pct, width=32):
    pct = max(0, min(100, int(pct or 0)))
    filled = pct * width // 100
    return "[" + "█" * filled + "░" * (width - filled) + "]"

stage = p.get('stage', '?')
stage_sec = p.get('stage_sec', 0)
audio_pct = p.get('audio_processed_pct', 0)
audio_proc = p.get('audio_processed_sec', 0)
audio_total = p.get('audio_sec', 0)
audio_src = p.get('audio_source', '?')
eta_rem = p.get('eta_remaining_sec', 0)
eta_src = p.get('eta_source', '?')
elapsed = p.get('elapsed_sec', 0)
warmup = p.get('warmup_sec', 0)
chip = p.get('chip', '?')
last_log = (p.get('last_log') or '').strip()[:90]

# Human-readable stage description — pyannote/whisperX use opaque names; explain inline.
stage_help = {
    'init': 'initializing',
    'extract': 'extracting audio (ffmpeg)',
    'transcribe': 'transcribing (whisperX streams segments)',
    'align': 'word-level alignment (whisperX)',
    'diarize': 'speaker diarization (pyannote) — silent step, no per-token output',
    'finalize': 'rendering Markdown',
    'done': 'finished',
}.get(stage, stage)

print(f"[scriba] {os.path.basename(in_path)}")
print(f"  chip: {chip}")
print()
print(f"  stage:    {stage} — {stage_help}   ({fmt(stage_sec)} in this stage)")
if stage == 'transcribe':
    print(f"  audio:    {bar(audio_pct)} {audio_pct:>3}%   ({fmt(audio_proc)} / {fmt(audio_total)})   [{audio_src}]")
    print(f"  ETA:      {fmt(eta_rem)} remaining   [{eta_src}]")
else:
    # No reliable per-step % for align/diarize/extract/finalize — show audio_total instead so
    # the user remembers what's being processed.
    print(f"  audio:    {fmt(audio_total)} total   (transcribe stage already done)" if stage in ('align','diarize','finalize') else f"  audio:    {fmt(audio_total)} total")
    print(f"  ETA:      — (no reliable estimate for this stage)")
print(f"  elapsed:  {fmt(elapsed)} (warmup {fmt(warmup)})")
print(f"  log:      {last_log}")
print()
print("  Ctrl-C to detach. Transcription keeps running.")
if stage == 'done':
    print()
    print("  ✓ DONE — transcript is ready.")
    print("__DONE__")
PY
)
    clear
    # Strip sentinel before printing; sentinel signals exit.
    printf '%s\n' "${rendered%$'\n'__DONE__*}" | sed -n '/__BUSY__/!p'
    if [[ "$rendered" == *"__DONE__"* ]]; then
      tput cnorm 2>/dev/null
      exit 0
    fi
    sleep 2
  done
fi

# ---- --status: one-line progress, cheap to poll (no token cost for AI) ----
if [[ "${1:-}" == "--status" ]]; then
  [[ -n "${2:-}" && -f "${2}" ]] || { echo "Usage: transcribe.sh --status <media-file>" >&2; exit 1; }
  IN="$2"
  STEM_S="$(basename "${IN%.*}")"
  PROG="$(dirname "$IN")/$STEM_S.transcript.progress.json"
  if [[ ! -f "$PROG" ]]; then
    # Disambiguate "not started yet" from "finished + cleaned up" by looking for the
    # final transcript.md inside the per-recording folder (C6). Default-case output stem
    # is the kebab of the input stem; with --title the names differ, but the agent knows
    # the title in that case — default detection is the path that matters here.
    OUT_STEM_S="$(python3 "$SKILL_DIR/scripts/naming.py" stem "$STEM_S" 2>/dev/null || echo "$STEM_S")"
    TRANSCRIPT_OUT="$(dirname "$IN")/$OUT_STEM_S.transcript/$OUT_STEM_S.md"
    if [[ -f "$TRANSCRIPT_OUT" ]]; then
      echo "stage=done · transcript: $TRANSCRIPT_OUT"
      exit 0
    fi
    echo "no progress file yet at $PROG" >&2
    exit 1
  fi
  python3 - "$PROG" <<'PY'
import json, sys
try:
    p = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"progress file invalid: {e}", file=sys.stderr); sys.exit(1)
def fmt(s):
    s = int(s or 0)
    return f"{s//60:02d}:{s%60:02d}"
tail = (p.get('last_log') or '').strip()[:80]
audio_pct = p.get('audio_processed_pct', 0)
audio_src = p.get('audio_source', '?')  # measured | extrapolated
wall_pct = p.get('pct', 0)
eta_src = p.get('eta_source', '?')      # observed | calibrated | chip_default | fallback
print(f"stage={p.get('stage','?')} · elapsed {fmt(p.get('elapsed_sec'))} · ETA {fmt(p.get('eta_remaining_sec'))} ({eta_src}) · audio {audio_pct}% ({audio_src}) · wall {wall_pct}% · {tail}")
PY
  exit 0
fi

[[ "${1:-}" == "--bootstrap" ]] && { bootstrap; exit 0; }
[[ $# -ge 1 && -f "${1:-}" ]] || usage

INPUT="$1"; shift
DEVICE="cpu"; MODEL="large-v3"; SPEAKERS=""; LANG=""; OUTDIR="$(dirname "$INPUT")"; TITLE=""; ASR="whisperx"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast) DEVICE="mlx"; shift;;
    --speakers) SPEAKERS="$2"; shift 2;;
    --enroll) ENROLL="$2"; shift 2;;
    --lang) LANG="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --asr) ASR="$2"; shift 2;;
    --out-dir) OUTDIR="$2"; shift 2;;
    --title|--name) TITLE="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; usage;;
  esac
done

# Auto-select GigaAM-RU only when Russian is FORCED and the opt-in env is set, and
# the caller didn't already pick a backend. GigaAM is RU-only (~-50% WER vs Whisper);
# the default stays whisperX large-v3. The MLX/--fast path is Whisper-only (no MLX
# GigaAM path) and is handled by the DEVICE==mlx branch below.
if [[ "${ASR:-whisperx}" == "whisperx" && "$LANG" == "ru" && "${SCRIBA_RU_GIGAAM:-0}" == "1" ]]; then
  ASR="gigaam"
fi

bootstrap  # idempotent

TMP="$(mktemp -d)"
ANNOTATE=(); HF_ARGS=()
if [[ -f "$HF_TOKEN_FILE" ]]; then
  ANNOTATE=(-a); HF_ARGS=(-hf "$(cat "$HF_TOKEN_FILE")")
else
  echo "WARN: no HF token at $HF_TOKEN_FILE — running WITHOUT speaker separation." >&2
fi
[[ -n "$SPEAKERS" ]] && SPK_ARGS=(-num "$SPEAKERS") || SPK_ARGS=()
[[ -n "$LANG" ]] && LANG_ARGS=(-l "$LANG") || LANG_ARGS=()

INPUT_ABS="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
STEM="$(basename "${INPUT%.*}")"
PROGRESS="$OUTDIR/$STEM.transcript.progress.json"
LOG="$OUTDIR/$STEM.transcript.log"
: > "$LOG"

# Normalize ANY audio/video to 16kHz mono WAV via ffmpeg.
command -v ffmpeg >/dev/null || { echo "ERROR: ffmpeg not found on PATH" >&2; exit 4; }

# Audio duration (sec).
AUDIO_SEC=0
if command -v ffprobe >/dev/null 2>&1; then
  AUDIO_SEC=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$INPUT_ABS" 2>/dev/null | awk '{print int($1)}')
  AUDIO_SEC="${AUDIO_SEC:-0}"
fi

# Chip detection (macOS) + factor from eta_helper.py (chip table → calibration cache override).
CHIP="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo unknown)"
FACTOR_INFO="$(python3 "$ETA_HELPER" factor "$DEVICE" "$MODEL" "$CHIP" "$CALIB_FILE" 2>/dev/null || echo "5.0|fallback|error")"
FACTOR="$(echo "$FACTOR_INFO" | cut -d'|' -f1)"
ETA_SOURCE="$(echo "$FACTOR_INFO" | cut -d'|' -f2)"
CHIP_LABEL="$(echo "$FACTOR_INFO" | cut -d'|' -f3)"
ETA_SEC=$(awk -v a="$AUDIO_SEC" -v f="$FACTOR" 'BEGIN { print int(a*f) }')

fmt_time() { local s=$1; printf "%02d:%02d" $((s/60)) $((s%60)); }

{
  echo "=============================================================="
  echo "[scriba]"
  printf "  audio:    %s (%ds)\n" "$(fmt_time "$AUDIO_SEC")" "$AUDIO_SEC"
  echo  "  pipeline: $MODEL · $DEVICE on $CHIP_LABEL"
  printf "  factor:   %s× (%s)\n" "$FACTOR" "$ETA_SOURCE"
  printf "  ETA:      ~%s wall-clock (refined after model warmup)\n" "$(fmt_time "$ETA_SEC")"
  echo  "  progress: $PROGRESS"
  echo  "  log:      $LOG"
  echo  "  status:   bash $(basename "${BASH_SOURCE[0]}") --status \"$INPUT_ABS\""
  echo "=============================================================="
} >&2

# Register this run for the Claude Code statusline (claude-hud picks it up via --extra-cmd).
# The pointer survives crashes; the statusline script will see stage=done (or no file at all)
# and just go silent in those cases.
mkdir -p "$HOME/.cache/scriba" 2>/dev/null || true
echo "$PROGRESS" > "$HOME/.cache/scriba/active" 2>/dev/null || true

# ---- background ticker: writes progress.json every 5s ----
STAGE_FILE="$TMP/stage"
echo "init" > "$STAGE_FILE"
START_TS=$(date +%s)

# True iff $LOG (silent) contains any of the given extended-regex alternatives.
log_has() { grep -qE "$1" "$LOG" 2>/dev/null; }

(
  set +e  # ticker must never kill the script
  HB_TICK=0; HB_LAST=""   # stdout status-heartbeat throttle (keeps "Shell details" live)
  WARMUP_AT=0          # elapsed_sec when "Transcribing" first appears in log
  TRANSCRIBE_DONE_AT=0 # elapsed_sec when alignment starts (transcribe loop is done)
  PREV_STAGE=""        # for detecting sub-stage transitions inside the wrapper
  STAGE_AT=0           # elapsed_sec when the current stage started
  while kill -0 $$ 2>/dev/null; do
    NOW=$(date +%s); EL=$((NOW - START_TS))

    # Detect "transcribing" stage start (whisply's "→ Transcribing" or our wrapper's
    # "→ transcribing"). Marks end of model load + language detect.
    if [[ $WARMUP_AT -eq 0 ]] && grep -qi "→ transcribing" "$LOG" 2>/dev/null; then
      WARMUP_AT=$EL
      echo "$WARMUP_AT" > "$TMP/warmup"
    fi
    # End of transcribe stage — whisply's "→ Annotating" or our wrapper's
    # "→ loading alignment model" (whichever appears first means the decoding loop is done).
    if [[ $TRANSCRIBE_DONE_AT -eq 0 ]] && log_has "→ Annotating|→ loading alignment model"; then
      TRANSCRIBE_DONE_AT=$EL
    fi

    # Real audio position from whisperX per-segment verbose lines.
    # Format: `Transcript: [<start> --> <end>] <text>` — take the last `end`.
    AUDIO_POS=$(grep -oE 'Transcript:\s*\[[0-9.]+\s*-->\s*[0-9.]+\]' "$LOG" 2>/dev/null \
                  | tail -1 | sed -E 's/.*--> *([0-9.]+).*/\1/' | awk '{print int($1)}')
    AUDIO_POS="${AUDIO_POS:-0}"

    # audio_processed_sec: prefer the real signal; fall back to factor-extrapolation
    # (used for MLX path and during warmup before any segment lands).
    AUDIO_SOURCE="extrapolated"
    if [[ $TRANSCRIBE_DONE_AT -gt 0 ]]; then
      AUDIO_PROC=$AUDIO_SEC
      AUDIO_SOURCE="measured"
    elif [[ $AUDIO_POS -gt 0 ]]; then
      AUDIO_PROC=$AUDIO_POS
      AUDIO_SOURCE="measured"
      (( AUDIO_PROC = AUDIO_PROC > AUDIO_SEC ? AUDIO_SEC : AUDIO_PROC ))
    elif [[ $WARMUP_AT -gt 0 && $AUDIO_SEC -gt 0 ]]; then
      TRANS_EL=$((EL - WARMUP_AT))
      AUDIO_PROC=$(awk -v t="$TRANS_EL" -v f="$FACTOR" 'BEGIN { print int(t/f) }')
      (( AUDIO_PROC = AUDIO_PROC > AUDIO_SEC ? AUDIO_SEC : AUDIO_PROC ))
    else
      AUDIO_PROC=0
    fi
    if [[ $AUDIO_SEC -gt 0 ]]; then AUDIO_PCT=$(( AUDIO_PROC * 100 / AUDIO_SEC )); else AUDIO_PCT=0; fi

    # ETA: prefer extrapolation from observed rate (real audio pos / transcribe elapsed).
    # Fall back to warmup-refined chip factor, then to the initial banner estimate.
    if [[ $AUDIO_POS -gt 5 && $WARMUP_AT -gt 0 ]]; then
      TRANS_EL=$((EL - WARMUP_AT))
      # remaining_wall = (audio_sec - audio_pos) × trans_el / audio_pos
      ETA_TOTAL=$(awk -v el="$EL" -v a="$AUDIO_SEC" -v p="$AUDIO_POS" -v t="$TRANS_EL" \
                    'BEGIN { print int(el + (a-p)*t/p) }')
      ETA_SOURCE_NOW="observed"
    elif [[ $WARMUP_AT -gt 0 ]]; then
      ETA_TOTAL=$(awk -v w="$WARMUP_AT" -v a="$AUDIO_SEC" -v f="$FACTOR" \
                    'BEGIN { print int(w + a*f) }')
      ETA_SOURCE_NOW="$ETA_SOURCE"
    else
      ETA_TOTAL=$ETA_SEC
      ETA_SOURCE_NOW="$ETA_SOURCE"
    fi
    REM=$(( ETA_TOTAL - EL )); (( REM = REM < 0 ? 0 : REM ))
    if [[ $ETA_TOTAL -gt 0 ]]; then
      PCT=$(( EL * 100 / ETA_TOTAL )); (( PCT = PCT > 99 ? 99 : PCT ))
    else
      PCT=0
    fi

    STG=$(cat "$STAGE_FILE" 2>/dev/null || echo unknown)
    # Refine the high-level "transcribe" super-stage into align/diarize sub-stages based on
    # log markers from the wrapper. Order matters — check the latest transition first.
    if [[ "$STG" == "transcribe" ]]; then
      if log_has "→ diarization done"; then
        STG="diarize"  # finished, but bash hasn't flipped to finalize yet
      elif log_has "→ diarize/|→ diarizing|→ loading pyannote model|→ assigning speakers"; then
        STG="diarize"
      elif log_has "→ alignment done"; then
        STG="diarize"  # transitional window between align-done and diarize-start
      elif log_has "→ loading alignment model|→ alignment in progress"; then
        STG="align"
      fi
    fi

    # Pyannote sub-step (only meaningful when STG=diarize). Format from wrapper's
    # TextProgressHook:  "→ diarize/<step_name> <pct>% (<completed>/<total>)"
    DIARIZE_STEP=""
    DIARIZE_PCT=0
    if [[ "$STG" == "diarize" ]]; then
      LATEST=$(grep -oE 'diarize/[a-z_]+ [0-9]+%' "$LOG" 2>/dev/null | tail -1)
      if [[ -n "$LATEST" ]]; then
        DIARIZE_STEP=$(echo "$LATEST" | sed -E 's@diarize/([a-z_]+) [0-9]+%@\1@')
        DIARIZE_PCT=$(echo "$LATEST" | sed -E 's@diarize/[a-z_]+ ([0-9]+)%@\1@')
      fi
    fi
    # Stage transition → reset stage timer
    if [[ "$STG" != "$PREV_STAGE" ]]; then
      PREV_STAGE="$STG"
      STAGE_AT=$EL
    fi
    STAGE_SEC=$((EL - STAGE_AT))

    # Compact status heartbeat -> stdout, so Claude Code's "Shell details" snapshot
    # (and any plain capture) shows current status even while whisperX/pyannote is
    # silent for tens of seconds. Emitted on stage/step change or every ~30s; the
    # verbose per-segment stream still goes to the log, not here.
    if [[ "$STG" == "transcribe" ]]; then
      HB="🎙 transcribe ${AUDIO_PCT}% (audio) · $(fmt_time "$EL") elapsed · ETA $(fmt_time "$REM")"
      HB_KEY="t:$((AUDIO_PCT/5))"
    elif [[ -n "$DIARIZE_STEP" ]]; then
      HB="🎙 ${STG}/${DIARIZE_STEP} ${DIARIZE_PCT}% · $(fmt_time "$STAGE_SEC") in stage · $(fmt_time "$EL") elapsed"
      HB_KEY="d:${DIARIZE_STEP}:$((DIARIZE_PCT/10))"
    else
      HB="🎙 ${STG} · $(fmt_time "$STAGE_SEC") in stage · $(fmt_time "$EL") elapsed"
      HB_KEY="s:${STG}"
    fi
    HB_TICK=$((HB_TICK + 1))
    if [[ "$HB_KEY" != "$HB_LAST" ]] || (( HB_TICK % 6 == 0 )); then
      echo "$HB" >&2; HB_LAST="$HB_KEY"   # stderr: keep stdout clean for the final `echo "$OUT"`
    fi

    # `cut -c` on macOS counts BYTES not characters, which corrupts multi-byte UTF-8
    # (Cyrillic, CJK, …) by chopping mid-character — that breaks the JSON. iconv with
    # UTF-8//IGNORE drops trailing broken bytes before they reach the JSON line.
    LAST=$(tail -c 600 "$LOG" 2>/dev/null \
            | tr '\r' '\n' \
            | grep -v '^[[:space:]]*$' \
            | tail -1 \
            | tr -d '"\\' \
            | tr '\t' ' ' \
            | head -c 240 \
            | iconv -f UTF-8 -t UTF-8//IGNORE 2>/dev/null)
    cat > "$PROGRESS" <<JSON
{"stage":"$STG","stage_sec":$STAGE_SEC,"diarize_step":"$DIARIZE_STEP","diarize_step_pct":$DIARIZE_PCT,"elapsed_sec":$EL,"audio_sec":$AUDIO_SEC,"audio_processed_sec":$AUDIO_PROC,"audio_processed_pct":$AUDIO_PCT,"audio_source":"$AUDIO_SOURCE","eta_total_sec":$ETA_TOTAL,"eta_remaining_sec":$REM,"pct":$PCT,"warmup_sec":$WARMUP_AT,"factor":$FACTOR,"eta_source":"$ETA_SOURCE_NOW","chip":"$CHIP_LABEL","started_at":$START_TS,"last_log":"$LAST"}
JSON
    sleep 5
  done
) &
TICKER_PID=$!
trap 'kill $TICKER_PID 2>/dev/null || true; rm -rf "$TMP"; rm -f "$HOME/.cache/scriba/active"' EXIT

# ---- pipeline ----
AUDIO="$TMP/audio.wav"

echo "extract" > "$STAGE_FILE"
echo "[1/3] Extracting audio (ffmpeg) ..." >&2
ffmpeg -y -i "$INPUT_ABS" -vn -ac 1 -ar 16000 "$AUDIO" >>"$LOG" 2>&1 \
  || { echo "ERROR: ffmpeg failed to extract audio from $INPUT_ABS" >&2; exit 4; }

echo "transcribe" > "$STAGE_FILE"
echo "[2/3] Transcribing ($DEVICE, $MODEL) — live output: tail -f \"$LOG\"" >&2

JSON="$TMP/audio.json"
if [[ "$DEVICE" == "mlx" ]]; then
  # MLX path: whisperX-py has no native MLX backend, so we keep whisply for --fast.
  # No real per-segment streaming, but MLX is fast enough that progress matters less.
  # The fast path can't apply enrollment or glossary biasing (those live on the
  # accuracy/whisperX path) — warn rather than silently ignore them.
  if [[ -n "${ENROLL:-}" ]] || [[ -n "$(python3 "$SKILL_DIR/scripts/glossary.py" --resolve "$OUTDIR" 2>/dev/null)" ]]; then
    echo "WARN: --enroll and glossary biasing are NOT applied on the --fast/MLX path; drop --fast to use them." >&2
  fi
  ( cd "$TMP" && KMP_DUPLICATE_LIB_OK=TRUE "$WHISPLY" run \
      -f "$AUDIO" -o "$TMP" -m "$MODEL" --device "$DEVICE" --export json \
      ${ANNOTATE[@]+"${ANNOTATE[@]}"} ${HF_ARGS[@]+"${HF_ARGS[@]}"} \
      ${SPK_ARGS[@]+"${SPK_ARGS[@]}"} ${LANG_ARGS[@]+"${LANG_ARGS[@]}"} ) 2>&1 | tee -a "$LOG" \
    || echo "WARN: whisply exited non-zero (often the cosmetic path-print bug); checking for JSON..." >&2
  JSON="$(find "$TMP" -name '*.json' | head -1)"
else
  # CPU path: call whisperX directly via our wrapper. verbose=True emits
  # `Transcript: [<start> --> <end>] <text>` for each segment as it's decoded —
  # the ticker parses this for REAL audio_position_sec, hardware-independent.
  WRAP_ARGS=(--audio "$AUDIO" --output "$JSON" --model "$MODEL" --device "$DEVICE" --batch-size 1 --asr "$ASR")
  [[ -n "$LANG" ]] && WRAP_ARGS+=(--language "$LANG")
  if [[ -f "$HF_TOKEN_FILE" ]]; then
    WRAP_ARGS+=(--annotate --hf-token "$(cat "$HF_TOKEN_FILE")")
  fi
  [[ -n "$SPEAKERS" ]] && WRAP_ARGS+=(--num-speakers "$SPEAKERS")
  [[ -n "${ENROLL:-}" ]] && WRAP_ARGS+=(--enroll "$ENROLL")
  # Glossary biasing (C5a): project-scoped ($OUTDIR/.scriba/glossary.txt) over global
  # (~/.config/scriba/glossary). Passed as initial_prompt/hotwords to bias decoding.
  GLOSSARY="$(python3 "$SKILL_DIR/scripts/glossary.py" --resolve "$OUTDIR" 2>/dev/null || true)"
  [[ -n "$GLOSSARY" ]] && WRAP_ARGS+=(--glossary "$GLOSSARY")
  # `-u` is critical: without it Python block-buffers stdout when piped to tee,
  # so the `Transcript: [...]` per-segment lines pile up in a 4 KB buffer and
  # only flush at process exit — defeating the whole point of streaming progress.
  PYTHONUNBUFFERED=1 "$PY" -u "$SKILL_DIR/scripts/transcribe_whisperx.py" "${WRAP_ARGS[@]}" 2>&1 | tee -a "$LOG" \
    || echo "WARN: wrapper exited non-zero; checking for JSON..." >&2
fi

[[ -n "$JSON" && -f "$JSON" ]] || { echo "ERROR: transcription produced no JSON" >&2; exit 3; }

echo "finalize" > "$STAGE_FILE"
echo "[3/3] Rendering Markdown + audio clips ..." >&2

# C6: meaningful name (input stem, or agent --title when generic), portable folder layout.
RAW_STEM="$(basename "${INPUT%.*}")"
TITLE="${TITLE:-}"
OUT_STEM="$(python3 "$SKILL_DIR/scripts/naming.py" stem "$RAW_STEM" "$TITLE")"
REC_DIR="$OUTDIR/$OUT_STEM.transcript"
DATA_DIR="$REC_DIR/data"
mkdir -p "$DATA_DIR"
REC_ID="$OUT_STEM-$START_TS"
OUT="$REC_DIR/$OUT_STEM.md"
"$PY" "$SKILL_DIR/scripts/json_to_md.py" "$JSON" \
  --source "$(basename "$INPUT")" --title "$OUT_STEM" --id "$REC_ID" \
  --model "$MODEL (whisperX+pyannote)" \
  --audio "$INPUT_ABS" --media-dir "$DATA_DIR" --clips-rel "data" \
  > "$OUT"
cp "$JSON" "$DATA_DIR/transcript.json" 2>/dev/null || true

# Corpus index for the AI (hidden .scriba at the recordings root).
# One python read of the sidecar (was three): pull language + low_confidence_pct and
# assemble the entry in a single pass; argv6 is the JSON path.
ENTRY="$(python3 -c "import json,sys
try: d=json.load(open(sys.argv[6]))
except Exception: d={}
print(json.dumps({'id':sys.argv[1],'title':sys.argv[2],'date':sys.argv[3],'lang':d.get('language','auto'),'duration':int(sys.argv[4]),'folder':sys.argv[5],'low_conf_pct':float(d.get('low_confidence_pct',0))}))" \
  "$REC_ID" "$OUT_STEM" "$(date +%Y-%m-%d)" "$AUDIO_SEC" "$OUT_STEM.transcript" "$JSON" 2>/dev/null || true)"
[[ -n "$ENTRY" ]] && python3 "$SKILL_DIR/scripts/update_index.py" upsert "$OUTDIR/.scriba" "$ENTRY" 2>/dev/null || true

# Record observed factor — but only on files long enough for the per-audio-second rate
# to dominate the one-off warmup. Short clips would skew the cache toward optimism.
NOW=$(date +%s); EL=$((NOW - START_TS))
WARMUP_SEC=0
[[ -f "$TMP/warmup" ]] && WARMUP_SEC=$(cat "$TMP/warmup" 2>/dev/null || echo 0)
TRANSCRIBE_EL=$(( EL - WARMUP_SEC ))
[[ $TRANSCRIBE_EL -lt 1 ]] && TRANSCRIBE_EL=$EL  # fallback if warmup wasn't detected
if [[ $AUDIO_SEC -ge 60 && $TRANSCRIBE_EL -gt 10 ]]; then
  python3 "$ETA_HELPER" record "$DEVICE" "$MODEL" "$AUDIO_SEC" "$TRANSCRIBE_EL" "$CALIB_FILE" 2>/dev/null || true
fi

echo "done" > "$STAGE_FILE"
cat > "$PROGRESS" <<JSON
{"stage":"done","stage_sec":0,"elapsed_sec":$EL,"audio_sec":$AUDIO_SEC,"audio_processed_sec":$AUDIO_SEC,"audio_processed_pct":100,"audio_source":"measured","eta_total_sec":$EL,"eta_remaining_sec":0,"pct":100,"warmup_sec":$WARMUP_SEC,"factor":$FACTOR,"eta_source":"$ETA_SOURCE","chip":"$CHIP_LABEL","started_at":$START_TS,"last_log":"transcript ready"}
JSON

# macOS notification — fires regardless of which terminal/chat launched the run.
# Set NOTIFY=0 to silence (e.g. for unattended automation).
if [[ "${NOTIFY:-1}" != "0" ]] && command -v osascript >/dev/null 2>&1; then
  # Escape for AppleScript: replace any " in the path with ' to avoid breaking the string.
  OSA_SAFE_OUT="${OUT//\"/\'}"
  OSA_SAFE_INPUT="$(basename "$INPUT")"
  osascript -e "display notification \"$OSA_SAFE_OUT\" with title \"scriba\" subtitle \"$OSA_SAFE_INPUT · $(fmt_time "$EL")\" sound name \"Glass\"" 2>/dev/null || true
fi

# Success path reached → the diagnostic artefacts (log, progress.json) have served
# their purpose. Delete them so the user is left with only the human-facing output:
# the `<title>.transcript/` folder (`<title>.md` + `data/`). On any earlier failure we
# `exit` before this line, so the log stays on disk for post-mortem.
# Stop the ticker explicitly so it doesn't recreate progress.json in the race window.
kill $TICKER_PID 2>/dev/null || true
wait $TICKER_PID 2>/dev/null || true   # reap the ticker so no late line can trail stdout
rm -f "$LOG" "$PROGRESS"

echo "$OUT"   # MUST be the last line on stdout — callers parse it as the output path
