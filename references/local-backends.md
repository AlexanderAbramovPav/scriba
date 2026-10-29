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

## Opt-in: Nemotron 3.5 Transcribe

`--asr nemotron35` runs NVIDIA's Nemotron 3.5 Transcribe 30B-A4B speech-LLM through
NeMo-Speech.cpp on Metal. One native pass gives punctuated, cased text, CTC word
times and speaker tags. The glossary becomes the instruction suffix
`Possible terms: …` (the model has no phrase boosting). It is **opt-in, never a
default**: use it for non-Russian or mixed-language meetings. Russian stays on GigaAM,
and other languages stay on WhisperX, until Russian runs are measured.

```bash
bash scripts/transcribe.sh meeting.m4a --asr nemotron35 [--lang en]
```

- **Speakers:** the model's own tags are used (`nemotron-3.5-embedded` in the JSON
  `pipeline.diarizer`); Nemotron 3 is not run a second time. `--enroll`,
  `--speakers N` or `--diarizer pyannote` decode without tags and assign speakers
  with pyannote (HF token needed).
- **Limits:** at most one hour per file (longer input stops with an error before
  the model loads). Offline only, no streaming progress: the ETA is a factor
  estimate until decoding returns. Not measured on Russian; a run with `--lang ru`
  logs a warning.
- **Hardware:** about 20 GB peak memory (scriba's other paths use about 3 GB) and
  21.4 GB on disk. Tested on an M4 Max with 36 GB; close heavy apps first. It does not
  fit 16–24 GB Macs. NVIDIA's official platform is CUDA; the Metal path is upstream
  llama.cpp without speculative decoding.
- **Instruction:** the default prompt is the one measured on the EN/DE fixtures
  (punctuation, fillers kept, written numbers, `<spk:N>` tags). Set
  `SCRIBA_NEMOTRON35_INSTRUCTION` to test another; `{language}` expands to the
  `--lang` name.

### Install

1. **Runtime.** Speech-LLM support (NeMo-Speech.cpp #82) is only in the **nightly**
   pre-release (66d50d9, 2026-10-28, or newer); v0.2.0 lacks it. Download
   `nemo-speech-nightly-macos-aarch64-metal.tar.gz` and its `.sha256` from
   <https://github.com/NVIDIA/NeMo-Speech.cpp/releases/tag/nightly>, check the
   checksum, unpack it outside the repo (here:
   `~/.local/share/scriba/nemo-speech-nightly-66d50d9/`), and point
   `SCRIBA_NEMOTRON35_BIN` at its `bin/nemo-speech`. Your `nemo-speech` 0.2.0 for
   Nemotron 3 diarization can stay as is. Scriba checks that the binary supports
   `--instruction` and stops with an error otherwise.
2. **Weights.** Put both GGUF files in one directory; the decoder loads the encoder
   next to it. Default: `~/.cache/scriba/nemotron35/`. Elsewhere: set
   `SCRIBA_NEMOTRON35_MODEL` to the decoder path, or pass `--model <decoder.gguf>`.

   | File (AtomicChat/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-GGUF) | Bytes | SHA-256 |
   |---|--:|---|
   | `NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-AD-IQ4_NL.gguf` (decoder) | 19,678,656,672 | `0c47d4ab6c783e7606ec03714b354fab0b2052027a7ea1991e7e2d3009c345ad` |
   | `NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-Encoder-F16.gguf` | 1,670,410,080 | `4221029c8a565c4a80c507ffa760c716e595acf663f9f4273ce69910050e7ba2` |

   ```bash
   mkdir -p ~/.cache/scriba/nemotron35 && cd ~/.cache/scriba/nemotron35
   for f in AD-IQ4_NL Encoder-F16; do
     curl -LO "https://huggingface.co/AtomicChat/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-GGUF/resolve/main/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-$f.gguf"
   done
   shasum -a 256 *.gguf   # compare with the table
   ```

   The GGUF is a third-party conversion of NVIDIA's checkpoint (OpenMDW 1.1). Its
   published quality deltas were measured on CUDA, not on Metal or Russian.
   Converting the 67.5 GB BF16 checkpoint yourself needs about 130 GB free disk.

### Evidence

Scout evaluation on 2026-10-29 (M4 Max, 36 GB, weights cached), synthetic two-voice
dialogues without overlap; WhisperX already scores 0% WER on them, so they separate
backends on timing, speakers and speed only:

| Input | Backend | WER | DER (no collar) | Turn-boundary MAE | Wall time |
|---|---|--:|--:|--:|--:|
| EN 52.2 s | WhisperX turbo + Nemotron 3 (scriba CLI) | 0.0% | 1.30% | 0.053 s | 53.6 s |
| EN 52.2 s | Nemotron 3.5, native CLI | 0.0% | 1.15% | 0.046 s | 13.7 s |
| EN 52.2 s | `--asr nemotron35` (scriba CLI, this release) | 0.0% | 1.15% | 0.046 s | 38.5 s ¹ |
| DE 67.8 s | WhisperX turbo + Nemotron 3 (scriba CLI) | 0.0% | 3.86% | 0.145 s | 31.3 s |
| DE 67.8 s | Nemotron 3.5, native CLI | 0.0% | 1.48% | 0.034 s | 15.0 s |

¹ Includes the model load from disk (ASR 36.8 s) and Markdown/clip rendering. Single
observations; no Russian or real-call measurement yet.

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
