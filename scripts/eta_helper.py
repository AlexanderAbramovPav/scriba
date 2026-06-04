"""Estimate transcription wall-clock from chip + calibration cache.

ETA = audio_sec * factor.

`factor` is the wall-clock-per-audio-second ratio for CPU whisperX large-v3 (default mode).
For MLX mode (`--fast`), a single GPU factor is used.

Initial factors (anchored to one observed M4 Max run = 3.2×, scaled by relative CPU benchmarks):
the calibration cache overrides these after the first real run on each machine.
"""

import json
import pathlib
import sys

# CPU factors for whisperX large-v3 on Apple Silicon (audio_sec → wall_clock_sec multiplier).
# Pipeline: whisperX direct (FasterWhisper + int8 quantization) via transcribe_whisperx.py.
# Anchored: M4 Max observed ~1.0× on a 5-min file (Jun 2026). Other entries scaled by
# relative CPU performance; the calibration cache refines per-machine after the first
# successful run on ≥ 60 s of audio.
#
# Note: the OLD whisply-CLI pipeline was ~3× slower because it didn't quantize. If you
# revive that path or the user runs with --fast (MLX), these numbers won't apply.
CHIP_FACTORS_CPU = {
    'M1':       2.0,
    'M1 Pro':   1.7,
    'M1 Max':   1.5,
    'M1 Ultra': 1.3,
    'M2':       1.7,
    'M2 Pro':   1.5,
    'M2 Max':   1.3,
    'M2 Ultra': 1.2,
    'M3':       1.5,
    'M3 Pro':   1.3,
    'M3 Max':   1.2,
    'M4':       1.3,
    'M4 Pro':   1.1,
    'M4 Max':   1.0,
}
CPU_FALLBACK = 2.0   # conservative for unknown CPU (incl. Intel)
MLX_FACTOR = 0.5     # MLX mode — faster than realtime on any Apple Silicon


def _match_chip(brand: str) -> str | None:
    """Return the most specific chip key that appears in the sysctl brand string."""
    for key in sorted(CHIP_FACTORS_CPU, key=len, reverse=True):
        if key in brand:
            return key
    return None


def get_factor(device: str, model: str, chip: str, calib_path: str) -> tuple[float, str, str]:
    """Return (factor, source, label). source ∈ {calibrated, chip_default, fallback}."""
    if device == 'mlx':
        base, source, label = MLX_FACTOR, 'chip_default', 'MLX'
    else:
        chip_key = _match_chip(chip)
        if chip_key:
            base, source, label = CHIP_FACTORS_CPU[chip_key], 'chip_default', chip_key
        else:
            base, source, label = CPU_FALLBACK, 'fallback', 'unknown CPU'

    p = pathlib.Path(calib_path)
    if p.exists():
        try:
            data = json.loads(p.read_text())
            key = f'{device}:{model}'
            entry = data.get(key)
            if entry and entry.get('runs', 0) >= 1:
                return entry['factor'], 'calibrated', label
        except Exception:
            pass
    return base, source, label


def record(device: str, model: str, audio_sec: float, elapsed_sec: float, calib_path: str) -> None:
    """Update calibration cache with an observed (audio_sec, elapsed_sec) datapoint.

    Uses an exponential moving average (alpha=0.4 after the first run) so the cache
    converges quickly but stays robust to one-off slow runs.
    """
    if audio_sec <= 0 or elapsed_sec <= 0:
        return
    observed = elapsed_sec / audio_sec
    p = pathlib.Path(calib_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(p.read_text()) if p.exists() else {}
    key = f'{device}:{model}'
    prev = data.get(key)
    if prev and prev.get('runs', 0) > 0:
        new_factor = 0.6 * prev['factor'] + 0.4 * observed
        runs = prev['runs'] + 1
    else:
        new_factor = observed
        runs = 1
    data[key] = {
        'factor': round(new_factor, 3),
        'runs': runs,
        'last_audio_sec': int(audio_sec),
        'last_elapsed_sec': int(elapsed_sec),
        'last_observed_factor': round(observed, 3),
    }
    p.write_text(json.dumps(data, indent=2))


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: eta_helper.py {factor|record} <args>', file=sys.stderr)
        return 1
    cmd = sys.argv[1]
    if cmd == 'factor':
        device, model, chip, calib = sys.argv[2:6]
        f, source, label = get_factor(device, model, chip, calib)
        print(f'{f:.3f}|{source}|{label}')
        return 0
    if cmd == 'record':
        device, model, audio_sec, elapsed_sec, calib = sys.argv[2:7]
        record(device, model, float(audio_sec), float(elapsed_sec), calib)
        return 0
    print(f'unknown command: {cmd}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
