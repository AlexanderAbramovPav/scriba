# ETA and performance measurements

The measured backend comparison is in
[README Performance](../README.md#performance--how-long-will-it-take) and
[the dated measurement record](../benchmarks/local-performance-2026-10-03.json).
This file describes the ETA code, including its remaining legacy heuristics.
An ETA heuristic is not a benchmark for the selected model.

## Calibration and its key

`transcribe.sh` looks up `~/.config/scriba/calibration.json` (or `CALIB_FILE`).
Entries are keyed by:

```
<ASR device>:<model>:<ASR backend>:<resolved diarizer>:<diarizer device>:<alignment option>
```

For example, GigaAM/Nemotron and full WhisperX/pyannote CPU do not share an
entry. Language is not a separate key. After a successful run with at least
60 s of audio and more than 10 s of recorded processing, the script records
`(local CLI elapsed - detected warmup) / audio_sec`. This includes remaining
local extraction/finalization work; it is not the same scope as the Python
`timings_sec.total` benchmark. If warmup was not detected, full elapsed time
is used. Later runs blend the old and new factor with an EMA (new weight 0.4).

The cache overrides the initial chip heuristic for that profile. It remains an
estimate: content, silence, speaker count, competing processes, initialization
and alignment-model availability can change the observed rate.

## Initial estimates — legacy values, not current-model benchmarks

Before profile calibration, `eta_helper.py` uses the following legacy CPU
values or the experimental MLX value. They are retained in code for an initial
banner estimate, not validated forecasts for GigaAM/Nemotron or WhisperX turbo.
They can substantially overestimate a fast profile. No measured hour-long
run or current cross-chip scaling is established by these values.

| Chip | Legacy CPU factor |
|---|---:|
| M1 | 2.0 |
| M1 Pro | 1.7 |
| M1 Max | 1.5 |
| M1 Ultra | 1.3 |
| M2 | 1.7 |
| M2 Pro | 1.5 |
| M2 Max | 1.3 |
| M2 Ultra | 1.2 |
| M3 | 1.5 |
| M3 Pro | 1.3 |
| M3 Max | 1.2 |
| M4 | 1.3 |
| M4 Pro | 1.1 |
| M4 Max | 1.0 |
| Unmatched CPU | 2.0 |
| Experimental MLX, any chip | 0.5 |

The initial banner uses `audio_sec * factor`. Once warmup is detected, the
predicted estimate adds it. These defaults are not a claim that MLX is twice as
fast on every Apple chip, or that an hour of current Russian ASR takes an hour.

## Live audio progress and observed-rate ETA

The ticker refreshes the progress JSON every 5 s. It reads the latest
`Transcript: [start --> end]` line from the selected backend as audio position.
WhisperX, GigaAM chunks and MLX can supply segment output; output availability
and buffering differ by backend.

The observed-rate ETA requires both an audio position above 5 s and the
`→ transcribing` warmup marker. It extrapolates:

```
remaining ≈ (audio_sec - audio_position) * decoding_elapsed / audio_position
```

If those signals are absent, the calibrated/legacy factor is used. In
particular, the RNNT wrapper currently logs `GigaAM-RU ASR` instead of the
`→ transcribing` marker: audio position can be measured while ETA stays based
on the factor. Do not promise an observed-rate ETA after every first segment.

Alignment and diarization are later stages without a reliable completion ETA.
Pyannote provides sub-step counters; Nemotron does not. Audio can reach 100%
before the transcript is ready. The macOS `done` notification refers to the
local CLI; host-AI punctuation runs separately and is not included.

## Progress fields

| Field | Meaning |
|---|---|
| `stage` | `init`, `extract`, `transcribe`, `align`, `diarize`, `finalize`, `done` |
| `stage_sec`, `elapsed_sec` | Current-stage and local-run elapsed time |
| `audio_sec`, `audio_processed_sec`, `audio_processed_pct` | Input duration and decoded audio position/progress |
| `audio_source` | `measured` from segment output/stage transition, or `extrapolated` |
| `eta_total_sec`, `eta_remaining_sec`, `pct` | Current estimate and capped wall-clock percentage, not a completion guarantee |
| `warmup_sec` | Detected warmup, zero if the marker was absent |
| `factor`, `eta_source`, `chip` | Initial/cache rate; source is `observed`, `calibrated`, `chip_default`, or `fallback` |
| `diarize_step`, `diarize_step_pct` | Pyannote sub-step when available; otherwise empty/zero |
| `last_log`, `started_at` | Latest diagnostic line and run start timestamp |

Success removes the diagnostic progress/log files. They are retained on failure.
For portable output paths, use the script's final stdout line (the Markdown
path) and [file layout](file-layout.md).

## Cache controls

- Set `CALIB_FILE=/path/to/cache.json` to isolate another calibration file.
- Remove your calibration cache to return to the legacy first-run estimates.
- Changing `eta_helper.py` constants changes those initial heuristics only;
  measured profile entries still take priority.
