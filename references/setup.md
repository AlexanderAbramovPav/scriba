# scriba — setup & notes

## One-time setup

1. Create a free [HuggingFace](https://huggingface.co) account.
2. Accept the user conditions for all gated models the pipeline pulls:
   - <https://huggingface.co/pyannote/segmentation-3.0> (MIT)
   - <https://huggingface.co/pyannote/speaker-diarization-community-1> (CC-BY-4.0 — attribution required if you redistribute output downstream; see `THIRD_PARTY_LICENSES.md`)
3. Create an access token at <https://hf.co/settings/tokens> (a **read** token is enough).
4. Store it (perms 600, outside git):
   ```bash
   mkdir -p ~/.config/scriba
   umask 077; printf '%s\n' '<YOUR_TOKEN>' > ~/.config/scriba/hf_token
   ```

Without the token, transcription still works but there is **no speaker separation**.

## Install (auto on first run)

The wrapper bootstraps an isolated venv on first use:
```bash
bash skills/scriba/scripts/transcribe.sh --bootstrap
```
This creates `skills/scriba/.venv` (Python 3.12 via `uv`) and installs
`whisply[mlx]` (pulls torch, torchaudio, pyannote, whisperX, and MLX).

## Engine / modes

- whisply auto-selects the backend; `--annotate` (speaker diarization) always routes through
  **whisperX + pyannote** for word-level timestamps, which on Apple Silicon runs on **CPU**.
- Default mode = accuracy (`--device cpu`, large-v3). `--fast` = MLX (GPU) transcription.

## Optional: GigaAM-RU backend (Russian only, opt-in)

GigaAM (salute-developers, Apache/MIT) is SOTA for Russian ASR — roughly **-50% WER vs
Whisper large-v3 on RU**. We run it through **sherpa-onnx** as a light ONNX transducer
(no NeMo runtime): the ONNX runtime + a ~240M model bundle, much lighter than full NeMo.
The default whisperX path is untouched; GigaAM is strictly opt-in and **Russian-only**.

### How to enable

- Explicit: `bash transcribe.sh <file> --lang ru --asr gigaam`
- Auto: force Russian and set the opt-in env — `SCRIBA_RU_GIGAAM=1 bash transcribe.sh <file> --lang ru`
  (the wrapper auto-selects `gigaam` only when both `--lang ru` and `SCRIBA_RU_GIGAAM=1`).

The `--fast`/MLX path stays Whisper — there is no MLX GigaAM path. Diarization
(pyannote community-1), C1 reconcile, C2 confidence, and C3 enrollment all run unchanged.

### One-time setup

1. Install the runtime into the skill venv:
   ```bash
   uv pip install --python skills/scriba/.venv/bin/python sherpa-onnx soundfile
   ```
2. Download a pre-exported sherpa-onnx GigaAM-RU **transducer** bundle into
   `~/.cache/scriba/gigaam/` (or set `SCRIBA_GIGAAM_DIR`). Verified working:
   [`sherpa-onnx-nemo-transducer-giga-am-v3-russian-2025-12-16`](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-transducer-giga-am-v3-russian-2025-12-16.tar.bz2)
   (~160 MB). Unpack so `encoder.int8.onnx`, `decoder.onnx`, `joiner.onnx`, `tokens.txt` sit
   directly in the model dir. (`asr_gigaam.py` auto-detects `encoder.onnx`/`encoder.int8.onnx`
   and loads it with `model_type="nemo_transducer"`.)

### Spike — confirm word timestamps (run once with a real RU clip)

**Verified (sherpa-onnx 1.13.2 + GigaAM v3 transducer, M4 Max):** the model emits
character-level `tokens` with per-char `timestamps`; `asr_gigaam` groups them into words.
Re-confirm on your own build/clip:
```bash
python3 skills/scriba/scripts/asr_gigaam.py --probe <ru_clip.wav>
# → needs_alignment=False words=N text[:60]='…'   (timestamps present)
# → needs_alignment=True  words=0 text[:60]='…'   (no timestamps)
```
If timestamps are present, GigaAM's word offsets feed diarization/reconcile directly.
If absent (`needs_alignment=True`), the wrapper **auto-falls-back** to aligning GigaAM's
text with whisperX's wav2vec aligner (`whisperx.align`) for the same word-level output —
so either spike outcome works. No code change needed either way.

## Troubleshooting

- **OpenMP / `libomp` crash** (`OMP: Error #15` or a hard abort): the wrapper already exports
  `KMP_DUPLICATE_LIB_OK=TRUE`. If running whisply manually, prefix the same env var.
- **ctranslate2 / torch version conflict** (per whisply docs): ensure `torch==2.8.0` and
  `torchaudio==2.8.0`, then `uv pip install --python skills/scriba/.venv/bin/python ctranslate2==4.6.0`.

## Observed JSON shape (whisply 0.14.1, captured 2026-05-31)

Top-level keys: `created, device, id, input_filepath, model, output_filepath, transcription, written_files`.

Transcript lives under `transcription.<lang>` (e.g. `transcription.ru`), which has:
- `text` — full plain transcript
- `text_with_speaker_annotation` — pre-formatted `[hh:mm:ss.mmm] [SPEAKER_00] text` lines
- `chunks[]` — the segments; each chunk = `{"text": str, "timestamp": [start, end], "words": [...]}`

**Speaker labels are on WORDS, not chunks.** Each word = `{"word", "start", "end", "score", "speaker"}`
with `speaker` like `SPEAKER_00`. The chunk-level `speaker` is absent/None.

`json_to_md.py::load_segments` therefore derives each chunk's speaker as the majority label
among its words (carrying the previous speaker forward for unlabeled chunks). It also still
supports the flat whisperX shape (`{"segments": [...]}` with per-segment `speaker`).

## Known cosmetic bug

whisply crashes at the end with `ValueError: ... is not in the subpath of ...` when the output
dir is not under the launch cwd (it prints `filepath.relative_to(cwd)`). The JSON is already
written before that print. `transcribe.sh` works around it by running whisply from inside the
output dir and tolerating a non-zero exit as long as a JSON file was produced.

## Dependency baseline (v0.1.0)

Tested on M4 Max with the following versions:
- `pyannote.audio==4.0.4`
- `whisperx==3.8.6`
- `torch==2.8.0`
- `transformers==4.57.6`
- diarization model: `pyannote/speaker-diarization-community-1` (CC-BY-4.0, gated on HF)
- VAD/segmentation model: `pyannote/segmentation-3.0` (MIT, gated on HF)
- ASR model: `large-v3` (MIT, OpenAI Whisper)

The default CPU path runs whisperX directly via `scripts/transcribe_whisperx.py`. The MLX
`--fast` path still goes through `whisply` if it's installed (whisply hasn't tracked
pyannote v4 yet — that's why we don't rely on it for the diarization path).

## torchcodec warning

pyannote.audio 4 imports torchcodec, which dlopen's a versioned libtorchcodec built against
FFmpeg 4-7. macOS Homebrew ffmpeg 8 ships only the FFmpeg 8 libs, so on import you'll see:
```
UserWarning: torchcodec is not installed correctly so built-in audio decoding will fail.
```
This is harmless for us: our wrapper preloads audio in-memory and passes it as a
`{'waveform': tensor, 'sample_rate': 16000}` dict, which is pyannote's documented
fallback for exactly this case. If you also want pyannote's file-loading path to work
(e.g. for other tools), install ffmpeg 7: `brew install ffmpeg@7`.
