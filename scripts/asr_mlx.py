"""Apple Silicon Whisper ASR with word timestamps in the shared Scriba pipeline."""
from __future__ import annotations


def model_repo(model: str) -> str:
    if "/" in model:
        return model
    if model in ("turbo", "large-v3-turbo"):
        return "mlx-community/whisper-large-v3-turbo"
    if model == "large-v3":
        return "mlx-community/whisper-large-v3-mlx"
    return f"mlx-community/whisper-{model}-mlx"


def transcribe(audio, model="large-v3-turbo", language=None, glossary=None, word_timestamps=True):
    import mlx_whisper
    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=model_repo(model), language=language,
        word_timestamps=word_timestamps, initial_prompt=glossary, verbose=True,
        without_timestamps=not word_timestamps,
        condition_on_previous_text=False,
    )
    # MLX reports word probability; downstream confidence expects `score`.
    for seg in result.get("segments", []):
        for word in seg.get("words", []):
            if "probability" in word:
                word["score"] = word["probability"]
    return result
