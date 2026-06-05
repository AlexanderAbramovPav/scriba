# Measure scriba's diarization accuracy on *your* audio

scriba does not ship a single headline "DER number", because the only honest
number is the one measured on audio like yours. This folder gives you a
zero-dependency way to produce that number yourself.

The metric is **Diarization Error Rate (DER)** — the standard "who spoke when"
score:

```
DER = (missed speech + false alarm + speaker confusion) / total reference speech
```

Lower is better. `0%` is perfect; research-grade open models land around
**10–11%** on clean benchmarks and higher on noisy, overlapping, multi-language
meetings.

`scripts/benchmark_der.py` implements DER in **pure Python (no third-party
deps)** — it runs on the same `python3` you already have. It uses the standard
definition with **optimal speaker-label mapping** (hyp speaker names are
arbitrary, so it tries every permutation and keeps the best) and is
**interval-based with no collar** (every millisecond counts; overlap is handled
via active-speaker counts).

## What's committed here

- `sample.rttm` — a tiny synthetic 2-speaker reference, so the RTTM format is
  concrete and you can sanity-check the scorer:

  ```bash
  # A reference scored against itself is, by definition, 0%.
  python3 scripts/benchmark_der.py benchmarks/sample.rttm benchmarks/sample.rttm
  # → DER = 0.00%
  ```

- **No audio files are committed** (size + privacy). You add your own.

## RTTM format

One line per speaker turn (whitespace-separated):

```
SPEAKER <file-id> 1 <start_sec> <duration_sec> <NA> <NA> <speaker-label> <NA> <NA>
```

Only columns 4 (`start`), 5 (`duration`), and 8 (`speaker-label`) matter to the
scorer. Speaker labels are arbitrary strings — `spk_A`, `Alice`, `1` — the
optimal-mapping step makes the *names* irrelevant; only the *partition* matters.

## Add a labeled pair and score it

1. Drop an audio/video file here, e.g. `my-meeting.wav` (or `.m4a`, `.mp4`, …).
2. Hand-label its reference as a sibling RTTM with the **same stem**:
   `my-meeting.rttm` — one line per turn, in the format above. (Tools like
   [ELAN](https://archive.mpi.nl/tla/elan) or Audacity labels exported by hand
   work fine for a few-minute clip.)
3. Score it end-to-end — this runs the full scriba pipeline, derives a
   hypothesis RTTM from the transcript sidecar's segment speakers, and compares
   it to your reference:

   ```bash
   python3 scripts/benchmark_der.py benchmarks/my-meeting.wav
   # → DER = 14.30%   (example)
   ```

   The derived hypothesis RTTM is written next to the produced transcript
   (`<title>.transcript/data/<stem>.hyp.rttm`) so you can inspect exactly where
   ref and hyp disagree.

You can also score two RTTM files directly (e.g. a hyp you produced elsewhere):

```bash
python3 scripts/benchmark_der.py reference.rttm hypothesis.rttm
```

## Recommended set

For a number that means something, include **at least one short clip per
language you care about** — e.g. one ~3-minute Russian meeting and one English
one, ideally with some cross-talk. A handful of representative clips beats one
long pristine recording. Keep the clips short enough to hand-label accurately;
labeling errors in the reference cap how low the measured DER can go.
