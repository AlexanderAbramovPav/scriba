# Contributing to scriba

Thanks for taking a look. This is a small, focused skill — a bash + Python pipeline around local ASR and diarization backends — so the contribution surface is intentionally narrow. The most impactful PR you can send is **a reproducible measurement for a specific hardware/backend profile**; second most is a clean bug report with reproducible state.

## Code of conduct

Be civil and assume good faith. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) v2.1. Personal attacks, harassment, or discriminatory comments will be removed; persistent offenders blocked.

## Reporting bugs

Open a GitHub issue. The more of the following you can include, the faster the bug gets fixed:

- **Skill version** — short git rev (`git rev-parse --short HEAD`) or release tag.
- **OS + chip** — `uname -a` (Linux) or `sw_vers && sysctl -n machdep.cpu.brand_string` (macOS).
- **Python + key package versions**:
  ```bash
  <skill>/.venv/bin/python --version
  uv pip list --python <skill>/.venv/bin/python
  ```
- **Input** — length of the source file (`ffprobe -v error -show_entries format=duration -of csv=p=0 <file>`) and any unusual properties (mixed languages, very long single utterances, music in the background, …). **Do not attach the source audio unless you're sure it's distributable** — privacy first.
- **The progress snapshot at failure** — `cat <stem>.transcript.progress.json`.
- **The last 50 lines of the log** — `tail -50 <stem>.transcript.log`. Strip any transcript text you don't want public.
- **Steps to reproduce** — the exact `transcribe.sh …` invocation, with all flags.

If you can reproduce on a small synthetic clip (e.g. a short locally synthesized dialogue or a public-domain recording), include that.

## Suggesting features

Open an issue first; PRs without prior discussion may be rejected if they don't fit the skill's narrow purpose. Things this skill *intentionally* does not do:

- Transcribe in the cloud (the whole point is local).
- Pre-process audio (denoise, EQ, etc.) — out of scope; do it before.
- Live-stream transcription — the pipeline is batch (a whole file).
- Drive third-party transcription APIs.

Things it should do well and where contributions are very welcome:

- Profile-specific measurements for other chips/CPUs, with initialization and timing scope stated.
- Recipes for additional statuslines in `references/statusline-integration.md`.
- Better handling of local diarizer/model errors and tested setup on other platforms.
- Bug fixes in `scripts/json_to_md.py` for edge cases in the whisperX/whisply JSON shapes.

## Contributing performance data

The [current README](README.md#performance--how-long-will-it-take) reports measured
runs for named profiles, not a chip-wide speed guarantee. The legacy chip table
in `eta_helper.py` is an initial ETA heuristic and should not be tuned from an
unrelated fast backend.

1. Use at least 60 s of audio, preferably several minutes. Record the language,
   duration, audio format, exact CLI flags, chip/RAM and package/runtime versions.
2. State the actual backend/model/device from `data/transcript.json` `pipeline`,
   whether weights were already cached, and whether initialization or concurrent
   work affected timing. `timings_sec.total` covers the Python pipeline, not
   extraction, Markdown/clip rendering or host-AI punctuation.
3. For comparisons, run profiles sequentially on the same input and hardware.
   The original CPU comparison can be selected with `--accurate --diarizer pyannote
   --diar-device cpu`. Repeat enough times to characterize variability if you
   report a typical rate; label a single observation as such.
4. Include the profile's calibration entry and/or an anonymized timing record.
   Do not publish audio, transcripts or voice references without permission.
5. Update the dated benchmark record/backend notes in a PR with the evidence.
   A WER/DER claim additionally needs checked verbatim text/speaker labels;
   output speaker counts or disagreement with another model are not accuracy.

## Local development

```bash
# clone (or have it under ~/.claude/skills/scriba via your install path)
git clone https://github.com/AlexanderAbramovPav/scriba
cd scriba

# bootstrap the venv
bash scripts/transcribe.sh --bootstrap

# pytest isn't a runtime dep — install it once for the dev venv
uv pip install --python .venv/bin/python pytest numpy

# run unit tests
.venv/bin/python -m pytest tests/ -v

# smoke test end-to-end on a short clip (provide your own)
bash scripts/transcribe.sh /path/to/short-clip.mp4
```

The unit suite covers rendering/renaming, JSON evidence, backend routing,
word/speaker preservation, enrollment helpers and punctuation guards. It runs
with only pytest/numpy; it does not download or evaluate ML models. Use a
separate real-audio smoke test when changing inference behavior.

## Code style

- **bash**: `set -euo pipefail` at the top of every script. Quote variables. Use `[[ ]]` over `[ ]`. Use `trap '...' EXIT` for cleanup. Don't shell out to `python3` if the value can be computed in pure bash; do shell out to a python helper if the logic is non-trivial (cf. `eta_helper.py`).
- **Python**: type hints encouraged but not enforced. No formatter pinned; aim for readability. f-strings over `%`. Standard library first, third-party only when justified.
- **General**: keep changes minimal and surgical. A bug fix doesn't need surrounding cleanup; a one-shot operation doesn't need a helper. Three similar lines is better than a premature abstraction. The bash + Python split is intentional — the bash is the orchestrator, the Python wrappers are the heavy lifters; don't blur the line.

## License of contributions

By submitting a pull request, you agree your contribution is licensed under the same [MIT License](./LICENSE) as the rest of the project. Don't include code you can't license under MIT (e.g. GPL'd snippets); ask first if in doubt.
