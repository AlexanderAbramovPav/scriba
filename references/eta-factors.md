# ETA model — how the wall-clock estimate is computed

There are **two regimes**:

1. **Live observed rate** (default CPU path, once the first segment lands). The wrapper `scripts/transcribe_whisperx.py` runs whisperX with `verbose=True`, so each finished segment prints `Transcript: [start --> end] text` to the log. The ticker takes the latest `end` as the real audio position and extrapolates:
   ```
   eta_remaining = (audio_sec − audio_position) × transcribe_elapsed / audio_position
   ```
   This is hardware-independent — no chip table, no factor, just real-time observation of the user's actual machine. Reported as `eta_source: observed` and `audio_source: measured`.

2. **Predicted from chip factor** (used for: the initial banner ETA before any segment lands; the warmup window before `→ transcribing` appears in the log; and the entire MLX `--fast` path because whisperX-py has no MLX backend and whisply doesn't stream per-segment timestamps). Linear model:
   ```
   wall_clock ≈ warmup + audio_sec × factor
   ```
   - **warmup** — model load + lang detect; observed at runtime when `→ transcribing` first appears.
   - **factor** — wall-clock seconds per second of audio during transcribe + annotate. From the chip table → calibration cache.

The ticker switches from regime (2) to regime (1) the moment any `Transcript: [...]` line shows up — typically within 10–30 s of the transcribe stage starting.

## Where the factor comes from

The script picks `factor` in this priority order:

1. **Calibration cache** (`~/.config/scriba/calibration.json`). Written automatically at the end of every successful run **≥ 60 s of audio**, using `(elapsed − warmup) / audio_sec` so the recorded factor is the pure per-audio-second rate and isn't skewed by warmup overhead. On the next run it overrides the chip table. After the first real run on a machine, the ETA is anchored to *that machine's* observed rate; subsequent runs blend in with an EMA (alpha 0.4).
2. **Chip table** in `scripts/eta_helper.py`. Indexed by the brand string returned by `sysctl -n machdep.cpu.brand_string` (e.g. `Apple M4 Max`).
3. **Fallback** of `2.0×` for CPUs that don't match any chip key (incl. Intel Macs).

For `--fast` (MLX) the chip table is bypassed entirely — a single `0.5×` factor is used, again refined by the cache.

## Chip table (CPU mode, whisperX large-v3 via `transcribe_whisperx.py` with int8 quant)

Anchored to **one observed M4 Max run ≈ 1.0×** (5-min audio, ~5:24 wall-clock, Jun 2026, batch_size=1, int8 compute_type, full pipeline incl. diarization). Other chips scaled from relative CPU performance. These are **starting estimates only** — used for the very first banner ETA on a new machine; the calibration cache replaces them with the observed factor after the first ≥60 s run, and the live ticker switches to `eta_source: observed` (no factor at all) the moment the first `Transcript: [...]` line lands in the log.

| Chip       | factor | rough wall-clock for 1 h audio |
| ---------- | -----: | -----------------------------: |
| M1         |  2.0×  |                           ~2 h |
| M1 Pro     |  1.7×  |                        ~1.7 h |
| M1 Max     |  1.5×  |                        ~1.5 h |
| M1 Ultra   |  1.3×  |                        ~1.3 h |
| M2         |  1.7×  |                        ~1.7 h |
| M2 Pro     |  1.5×  |                        ~1.5 h |
| M2 Max     |  1.3×  |                        ~1.3 h |
| M2 Ultra   |  1.2×  |                        ~1.2 h |
| M3         |  1.5×  |                        ~1.5 h |
| M3 Pro     |  1.3×  |                        ~1.3 h |
| M3 Max     |  1.2×  |                        ~1.2 h |
| M4         |  1.3×  |                        ~1.3 h |
| M4 Pro     |  1.1×  |                        ~1.1 h |
| M4 Max     |  1.0×  |                           ~1 h |
| MLX (any)  |  0.5×  |                          ~30 m |

The old `whisply run` CLI path (pre-Jun 2026) was ~3× slower because it didn't quantize. If your chip isn't here, the script uses `2.0×` and writes a calibrated factor after the first ≥60 s run. Contributions welcome — open a PR with the (chip, observed factor) pair.

## What gets reported live

Inside `<stem>.transcript.progress.json` (refreshed every 5 s):

| Field                  | Meaning |
| ---------------------- | ------- |
| `stage`                | init → extract → transcribe → finalize → done |
| `elapsed_sec`          | wall-clock since the script started |
| `audio_sec`            | total length of the input |
| `audio_processed_sec`  | position inside the audio. **Real measurement** once the wrapper emits its first `Transcript: [...]` line; before that, extrapolated from the chip factor |
| `audio_processed_pct`  | `audio_processed_sec / audio_sec × 100` |
| `audio_source`         | `measured` (from a real `Transcript: [<s> --> <e>]` line) · `extrapolated` (factor × elapsed) |
| `eta_total_sec`        | best current estimate of total wall-clock |
| `eta_remaining_sec`    | `eta_total - elapsed` (clamped at 0) |
| `pct`                  | `elapsed / eta_total × 100` (wall-clock progress, not audio progress) |
| `warmup_sec`           | observed warmup; `0` until `→ transcribing` appears in the log |
| `factor`               | factor in use (only meaningful when `audio_source = extrapolated`) |
| `eta_source`           | `observed` (real audio rate) · `calibrated` (cache) · `chip_default` (table) · `fallback` (unknown chip) |
| `chip`                 | resolved chip label, or `unknown CPU` |

## Why "audio %" and "wall %" can disagree

Until the log emits `→ transcribing`, audio_processed is `0` (we're still in model load + language detect — no audio has been touched yet), while wall_pct grows from 0 toward `warmup / eta_total`. Once whisperX emits its first `Transcript: [start --> end]` line — usually within 10–30 s of `→ transcribing` — `audio_processed_sec` flips to the real measured value, `audio_source` becomes `measured`, and `eta_source` becomes `observed`. After that the two percentages track tightly (`audio_pct` measures the audio side; `wall_pct` measures `elapsed/eta_total` and is recomputed against the observed rate, so they should agree within a few points unless the per-segment rate is wildly non-uniform).

On the MLX path (`--fast`) and on any future tool that doesn't stream per-segment timestamps, `audio_processed_sec` stays extrapolated for the whole run — that's the only case where the chip factor still matters for the live %.

## Manual override / reset

- Force a specific factor: edit `scripts/eta_helper.py` `CHIP_FACTORS_CPU` or `CPU_FALLBACK`.
- Wipe the calibration cache: `rm ~/.config/scriba/calibration.json` — the next run falls back to the chip table again.
- Use a custom cache path: set `CALIB_FILE=/path/to/cache.json` in the environment.
