# Contributing to scriba

Thanks for taking a look. This is a small, focused skill — a bash + Python wrapper around whisperX and pyannote — so the contribution surface is intentionally narrow. The most impactful PR you can send is **a new chip's measured `factor` for the speed benchmark table**; second most is a clean bug report with reproducible state.

## Code of conduct

Be civil and assume good faith. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) v2.1. Personal attacks, harassment, or discriminatory comments will be removed; persistent offenders blocked.

## Reporting bugs

Open a GitHub issue. The more of the following you can include, the faster the bug gets fixed:

- **Skill version** — short git rev (`git rev-parse --short HEAD`) or release tag.
- **OS + chip** — `uname -a` (Linux) or `sw_vers && sysctl -n machdep.cpu.brand_string` (macOS).
- **Python + key package versions**:
  ```bash
  <skill>/.venv/bin/python --version
  <skill>/.venv/bin/pip list | grep -iE "^(pyannote.audio|whisperx|faster-whisper|torch|transformers) "
  ```
- **Input** — length of the source file (`ffprobe -v error -show_entries format=duration -of csv=p=0 <file>`) and any unusual properties (mixed languages, very long single utterances, music in the background, …). **Do not attach the source audio unless you're sure it's distributable** — privacy first.
- **The progress snapshot at failure** — `cat <stem>.transcript.progress.json`.
- **The last 50 lines of the log** — `tail -50 <stem>.transcript.log`. Strip any transcript text you don't want public.
- **Steps to reproduce** — the exact `transcribe.sh …` invocation, with all flags.

If you can reproduce on a small synthetic clip (e.g. a 15 s ffmpeg-generated tone or a public-domain recording), include that.

## Suggesting features

Open an issue first; PRs without prior discussion may be rejected if they don't fit the skill's narrow purpose. Things this skill *intentionally* does not do:

- Transcribe in the cloud (the whole point is local).
- Pre-process audio (denoise, EQ, etc.) — out of scope; do it before.
- Live-stream transcription — the pipeline is batch (a whole file).
- Drive third-party transcription APIs.

Things it should do well and where contributions are very welcome:

- More accurate factors for non-M-series CPUs (Intel Macs, Linux x86, ARM Linux).
- Recipes for additional statuslines in `references/statusline-integration.md`.
- Better handling of pyannote.audio v4 once `community-1` has a clearer license path (see `references/setup.md`).
- Bug fixes in `scripts/json_to_md.py` for edge cases in the whisperX/whisply JSON shapes.

## Contributing speed-benchmark data for a new chip

This is the most valuable contribution path because the table in `README.md` is anchored to a single observed M4 Max run plus rough scaling. Real measurements from real hardware are gold.

1. Run `bash scripts/transcribe.sh <file>` on at least **60 seconds of audio** (preferably 5+ minutes — longer = warmup amortizes better) on the chip you want to characterize. Use the **default** flags (no `--fast`) so the measurement covers the full transcribe + align + diarize pipeline.
2. After it finishes, your calibration cache has the observed factor:
   ```bash
   cat ~/.config/scriba/calibration.json
   ```
3. Open a PR that:
   - Adds an entry to `scripts/eta_helper.py` `CHIP_FACTORS_CPU` for your chip key (the substring of `sysctl -n machdep.cpu.brand_string` that matches your chip, e.g. `"M3 Max"`, `"Intel Core i7-13700K"`).
   - Adds the same row to the table in `README.md` under "Performance — Apple Silicon CPU benchmark" (or extend the section for non-Apple chips).
   - In the PR description: paste the calibration cache JSON, your chip string, the audio length, the wall-clock you observed, and Python + pyannote.audio + whisperX versions used.

I'll merge a one-line PR fast; the more data points, the more accurate the ETA on first run for everyone.

## Local development

```bash
# clone (or have it under ~/.claude/skills/scriba via your install path)
git clone https://github.com/AlexanderAbramovPav/scriba
cd scriba

# bootstrap the venv
bash scripts/transcribe.sh --bootstrap

# pytest isn't a runtime dep — install it once for the dev venv
.venv/bin/pip install pytest

# run unit tests
.venv/bin/python -m pytest tests/ -v

# smoke test end-to-end on a short clip (provide your own)
bash scripts/transcribe.sh /path/to/short-clip.mp4
```

The tests cover `json_to_md.py` (whisply JSON shape → markdown) and `rename_speakers.py` (Speaker label substitution). New scripts should have a matching test if they have non-trivial logic.

## Code style

- **bash**: `set -euo pipefail` at the top of every script. Quote variables. Use `[[ ]]` over `[ ]`. Use `trap '...' EXIT` for cleanup. Don't shell out to `python3` if the value can be computed in pure bash; do shell out to a python helper if the logic is non-trivial (cf. `eta_helper.py`).
- **Python**: type hints encouraged but not enforced. No formatter pinned; aim for readability. f-strings over `%`. Standard library first, third-party only when justified.
- **General**: keep changes minimal and surgical. A bug fix doesn't need surrounding cleanup; a one-shot operation doesn't need a helper. Three similar lines is better than a premature abstraction. The bash + Python split is intentional — the bash is the orchestrator, the Python wrappers are the heavy lifters; don't blur the line.

## License of contributions

By submitting a pull request, you agree your contribution is licensed under the same [MIT License](./LICENSE) as the rest of the project. Don't include code you can't license under MIT (e.g. GPL'd snippets); ask first if in doubt.
