# Local backends on Apple Silicon

All backends feed the same word-level speaker assignment, reconciliation, confidence,
enrollment (when supported), Markdown and listening-clip renderer. Audio stays local.

## ASR

On this Mac, `--lang ru` selects GigaAM v3 RNNT ONNX int8 when the bundle is
installed and no glossary or model override is requested. It emits verbatim
Russian spelling without punctuation. The host AI can restore punctuation via
[the validated punctuation workflow](punctuation.md), preserving the raw version;
its chat time/tokens are additional to the local pipeline benchmark.
Other/auto languages use WhisperX
large-v3-turbo. `--accurate` restores the original full WhisperX decoder.


- `--asr gigaam3 --lang ru`: GigaAM v3 E2E CTC (`--model v3_e2e_ctc`), punctuation and
  native word timestamps, Apple MPS when available. Silero VAD splits at pauses into
  <=25 s clips required by GigaAM's public short-form API. Russian only; no glossary
  decoding bias. Unknown ASR confidence is `null`, never a fabricated 1.0.
- `--asr mlx --model large-v3`: full multilingual Whisper on Apple GPU, with forced
  wav2vec alignment by default. Experimental; review completeness on your audio.
- `--asr mlx --model large-v3-turbo`: faster pruned Whisper. Evaluate completeness on
  your own audio before selecting it for important recordings.
- `--fast`: MLX with native cross-attention word timestamps, skipping wav2vec alignment.
- `--asr whisperx --diarizer pyannote --diar-device cpu`: original CPU-compatible path.
- `--asr gigaam`: GigaAM v3 RNNT via sherpa-onnx, now with bounded VAD chunks.
  The former full-recording path exceeded the model positional limit on five
  minutes of audio; chunking fixes long-recording support and limits memory.

The full WhisperX model is still available with `--accurate`. MLX is experimental here:
Oscar tests showed phrase omissions even with full large-v3 and FP32. Do not
select it for important Russian recordings without reviewing completeness. An explicit `--asr`
always wins over language-based routing. See `transcribe.sh --help` for options.

## Diarization

For **every ASR language**, including auto-detected and mixed-language recordings,
`--diarizer auto` uses native Nemotron 3 when `nemo-speech` is on PATH or
`SCRIBA_NEMO_BIN` points to it. Otherwise it uses pyannote community-1, with MPS
when available. `--diar-device cpu` is available for comparison or compatibility.

Nemotron 3 supports up to eight distinct speakers. Its `v3-offline` preset uses
large streaming chunks and preserves state over long recordings. It is not the
full-attention `--offline` mode, which is limited to roughly 6.6 minutes.

`--enroll` or `--speakers N` automatically selects pyannote, since Nemotron does
not implement those controls. Requesting them with explicit `--diarizer nemotron`
produces an actionable error rather than ignoring them. Explicit backend failures
stop the run instead of publishing a misleading single-speaker transcript.

The shell entry point and direct Python wrapper share the same backend resolver.
Diarization consumes audio, without a language argument; multilingual ASR remains
WhisperX. This routing policy is not proof of equal diarization quality in every
language: evaluate a checked speaker reference for your recordings.

Speaker labels are anonymous. Short replies in any language are preserved; the pipeline
no longer changes every <400 ms isolated word to its neighbours' speaker.

## Reproduce this installation

Tested: Apple M4 Max / 36 GB, torch 2.8.0, pyannote.audio 4.0.4,
whisperx 3.8.6, mlx-whisper 0.4.3, NVIDIA NeMo-Speech.cpp 0.2.0 Metal.
GigaAM package pinned to commit `7447938d791c4f3e643386ee22c33777004293a5`.
The wrapper installs GigaAM's needed runtime dependencies on first selection.

Install NVIDIA's native runtime using the official instructions:
<https://github.com/NVIDIA/NeMo-Speech.cpp#installation>
The current machine uses a downloaded macOS aarch64 Metal release archive, checked
against its published SHA-256, under `~/.local/share/scriba/nemo-speech-0.2.0/`,
linked as `~/.local/bin/nemo-speech`. Models are cached by the native CLI and
verified by size and checksum. No HuggingFace token is needed for Nemotron.

Sources:
- <https://github.com/salute-developers/GigaAM>
- <https://huggingface.co/nvidia/Nemotron-3-Diarization>
- <https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/cli.md>
- <https://huggingface.co/openai/whisper-large-v3-turbo>

## Benchmark evidence

The local Oscar benchmark is at `~/Movies/scriba-benchmark-oscar/`.
Each new JSON includes `pipeline`, `timings_sec`, and raw `diarization_turns`.
Compare wall time only for sequential runs with weights already downloaded.
First Metal inference can include shader compilation; report it separately.
Do not call disagreement with another model WER or DER accuracy. Ground-truth
WER needs a checked verbatim transcript; DER needs a checked speaker RTTM.

Observed cached-weight Oscar 31:00–36:00 runs: original CPU pipeline 416.8 s;
GigaAM RNNT + Nemotron 31.3 s; GigaAM E2E CTC + Nemotron 55.9 s.
Nemotron and pyannote MPS each found five voice groups on this fragment;
models disagreed on some turns, and no ground-truth DER is asserted.

Final end-to-end checks on October 3, 2026 used the same Mac and automatic
diarizer selection:

| Input | Language choice | ASR | Diarizer | Audio | Pipeline time |
|---|---|---|---|---|---|
| Russian Oscar call, 31:00–36:00 | `--lang ru` | GigaAM v3 RNNT | Nemotron 3 | 300 s | 22.7 s |
| Synthetic English dialogue, six alternating turns | `--lang en` | WhisperX turbo | Nemotron 3 | 52.2 s | 51.6 s |
| Synthetic German dialogue, six alternating turns | auto-detected `de` | WhisperX turbo | Nemotron 3 | 67.8 s | 62.5 s |

English/German fixtures used two local macOS voices each, without overlap.
Both retained two distinct voice labels across all six turns; voice clips and
word timings were verified. This tests routing/integration, not real-call DER.
The Russian rerun retained the original recognized word sequence and five voice
groups. These pipeline times include ASR, alignment and model initialization;
they are separate checks, not a replacement for the earlier speed comparison.
Native diarization alone took about 0.5 s (English), 0.3 s (German), and 1.8 s
(Russian) on these runs. Host-AI punctuation is excluded.

The 97-test unit suite passed on Python 3.11 and 3.12, including the minimum
CI dependency set (`pytest`, `numpy`). Regression coverage exercises default
diarization for forced `ru/en/de/es/fr` and auto-detection, pyannote controls,
missing native runtime, short replies, raw text preservation and punctuation edits.

Published timing records (without audio/transcripts):
[October 3, 2026 measurements](../benchmarks/local-performance-2026-10-03.json).
