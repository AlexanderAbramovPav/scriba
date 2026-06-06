# Security Policy

scriba runs **entirely on your machine** — it never uploads audio or transcripts.
The security surface is the local pipeline (bash + Python) and its third-party
model/runtime dependencies (whisperX, pyannote.audio, faster-whisper, ffmpeg,
optionally sherpa-onnx). HuggingFace tokens are stored locally at
`~/.config/scriba/hf_token` with `chmod 600` and are never transmitted by scriba.

## Reporting a vulnerability

Please report privately via GitHub's
[private vulnerability reporting](https://github.com/AlexanderAbramovPav/scriba/security/advisories/new)
(repo **Security → Report a vulnerability**). If that is unavailable, open a
minimal issue **without** exploit details and ask for a private channel.

Please do **not** open a public issue containing a working exploit.

We aim to acknowledge reports within a few days.

## Supported versions

The latest release and `main` are supported. Fixes land on `main` and in the
next tagged release.
