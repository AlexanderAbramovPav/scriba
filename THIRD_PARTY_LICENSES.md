# Third-party licenses

`scriba` is licensed under the MIT License (see [`LICENSE`](./LICENSE)). It depends at runtime on the open-source projects listed below. **None of their source code or model weights is vendored in this repository** — everything is installed locally via `pip`/`uv` into a venv on first run, and the gated HuggingFace model weights are downloaded with the user's own HuggingFace token. The list is provided here for transparency and to honour the upstream attribution requirements (BSD-2-Clause in particular).

Versions captured from a clean bootstrap on Apple Silicon, June 2026.

## Python packages (installed via pip into `.venv/`)

| Component | Version pinned | License | Upstream | Notes |
|---|---|---|---|---|
| [whisperX](https://github.com/m-bain/whisperX) | 3.8.6 | **BSD-2-Clause** | [LICENSE](https://github.com/m-bain/whisperX/blob/main/LICENSE) | Word-level alignment + diarization orchestration on top of faster-whisper. BSD-2-Clause requires the copyright notice and disclaimer be preserved — reproduced below. |
| [pyannote.audio](https://github.com/pyannote/pyannote-audio) | 4.0.4 | MIT | [LICENSE](https://github.com/pyannote/pyannote-audio/blob/develop/LICENSE) | Speaker diarization library. v4 is the default in upstream whisperX 3.8+. |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | latest of 1.x | MIT | [LICENSE](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) | The actual ASR engine, underneath whisperX. |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | 4.x | MIT | [LICENSE](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) | Inference backend for faster-whisper (int8 quantization on CPU). |
| [OpenAI Whisper](https://github.com/openai/whisper) (model weights) | `large-v3` | MIT | [LICENSE](https://github.com/openai/whisper/blob/main/LICENSE) | Acoustic model weights distributed by OpenAI. |
| [whisply](https://github.com/transcriptionTeam/whisply) | 0.14.x | MIT | upstream README | Optional — only used by `--fast` (MLX) path. The default CPU path bypasses whisply and calls whisperX directly. |

## Gated HuggingFace model weights (downloaded with the user's HF token)

| Model | Version | License (on HF model card) | Notes |
|---|---|---|---|
| [`pyannote/segmentation-3.0`](https://huggingface.co/pyannote/segmentation-3.0) | 3.0 | MIT (gated) | Voice-activity detection + speaker segmentation. User must accept HF terms once. |
| [`pyannote/speaker-diarization-community-1`](https://huggingface.co/pyannote/speaker-diarization-community-1) | community-1 | **CC-BY-4.0** (gated) | Composite diarization pipeline (default for whisperX 3.8+, pyannote.audio 4.0+). Permissive — commercial use OK — but **attribution is required** (see below). User accepts HF terms once. |

"Gated" means HuggingFace requires acceptance of the model card terms once per account before the weights become downloadable. We download the weights at first run via the user's token. **We never bundle these weights in this repository or in any release artifact.**

### CC-BY-4.0 attribution for `pyannote/speaker-diarization-community-1`

If you ship transcripts produced with this skill (or build a product on top of it), include the following attribution in user-visible documentation, an "About" page, or a NOTICE/CREDITS section:

> Speaker diarization powered by [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) by Hervé Bredin / pyannoteAI, licensed under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).

If you modify the model (most users won't), CC-BY-4.0 also asks you to indicate that you've changed it.

## How to comply with BSD-2-Clause (whisperX)

If you redistribute a build of this skill (e.g. as a `.skill` archive or as part of a larger product), include the following whisperX attribution somewhere in your distribution (a `THIRD_PARTY_LICENSES.md`, `NOTICE`, or "About" panel is fine):

```
whisperX
Copyright (c) 2022, Max Bain
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

The MIT-licensed dependencies each require their license text and copyright notice to be retained in any redistribution. Since this skill does not vendor them, the obligation effectively falls to whoever bundles them downstream.

## System dependencies (not bundled)

- **`bash`** — shell. Distributed with macOS / Linux.
- **`ffmpeg` + `ffprobe`** ([LGPL/GPL hybrid](https://ffmpeg.org/legal.html), depending on build). Used by `transcribe.sh` for audio normalization and by `whisperx.load_audio` internally. Install via Homebrew / apt — this skill does not bundle ffmpeg.
- **`uv`** ([MIT/Apache-2.0](https://github.com/astral-sh/uv/blob/main/LICENSE-MIT)). Used for venv creation and pip installs. Install via the official uv installer.
- **Python 3.10+** (PSF License). Standard distribution.
