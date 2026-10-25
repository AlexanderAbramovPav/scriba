import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
# Imports cleanly without the ML stack: `import whisperx` is deferred into main(), and CI installs
# only pytest+numpy. This guards the regression in issue #3 (diarization died on pyannote 3.x).
import transcribe_whisperx as tw
import pytest


def test_pyannote_4x_is_ok():
    for v in ("4.0.0", "4.0.4", "4.1.0", "5.0.0"):
        ok, msg = tw.diarization_backend_ok(v)
        assert ok is True
        assert msg == ""


def test_pyannote_3x_is_rejected_with_actionable_message():
    # whisply pins pyannote.audio==3.4.0 → the version that broke for the issue reporter.
    for v in ("3.4.0", "3.1.1", "3.0.0"):
        ok, msg = tw.diarization_backend_ok(v)
        assert ok is False
        # Message must name the package and the required floor so the user can self-serve.
        assert "pyannote.audio" in msg
        assert ">=4.0" in msg
        assert v in msg


def test_unparseable_version_does_not_block():
    # Defensive: a weird/missing version string must not hard-fail the run — let the real call
    # (and its surrounding except) decide. Returns ok=True so we don't skip diarization spuriously.
    for v in ("", "unknown", None):
        ok, msg = tw.diarization_backend_ok(v)
        assert ok is True
        assert msg == ""


@pytest.mark.parametrize("language", [None, "ru", "en", "de", "es", "fr"])
def test_default_native_diarization_flows_through_every_language(monkeypatch, tmp_path, language):
    """Exercise the real wrapper routing/reconcile/output with stubbed ML inference."""
    import copy
    import json
    import numpy as np
    from types import SimpleNamespace
    import diarize_nemotron as dn
    detected = language or "de"
    raw = {"language": detected, "segments": [{"start": 0., "end": 4., "text": "hello yes",
            "words": [{"word": "hello", "start": .1, "end": 1., "score": .9},
                      {"word": "yes", "start": 2., "end": 2.2, "score": .9}]}]}
    turns = [(0., 1.5, "speaker_0"), (1.5, 4., "speaker_1")]
    calls = []
    def native(audio, device):
        calls.append((audio, device))
        return turns
    def assign(rows, result):
        assert rows == turns
        for seg in result["segments"]:
            seg["speaker"] = "speaker_0"
            for word in seg["words"]:
                word["speaker"] = "speaker_0" if word["start"] < 1.5 else "speaker_1"
        return result
    whisperx = SimpleNamespace(
        load_model=lambda *a, **kw: SimpleNamespace(transcribe=lambda *a, **kw: copy.deepcopy(raw)),
        load_audio=lambda path: np.zeros(64000, dtype=np.float32),
        load_align_model=lambda **kw: (None, None),
        align=lambda segments, *a, **kw: {"segments": segments},
        assign_word_speakers=assign)
    monkeypatch.setitem(sys.modules, "whisperx", whisperx)
    monkeypatch.setitem(sys.modules, "pandas", SimpleNamespace(DataFrame=lambda rows, **kw: rows))
    monkeypatch.setattr(dn, "executable", lambda: "/native/nemo-speech")
    monkeypatch.setattr(dn, "diarize", native)
    output = tmp_path / "out.json"
    argv = ["transcribe_whisperx.py", "--audio", "call.wav", "--output", str(output), "--annotate"]
    if language:
        argv += ["--language", language]
    monkeypatch.setattr(sys, "argv", argv)
    assert tw.main() == 0
    result = json.loads(output.read_text())
    assert result["language"] == detected
    assert result["pipeline"]["diarizer"] == "nemotron-3"
    assert result["diarization_turns"] == [{"start": s, "end": e, "speaker": p} for s, e, p in turns]
    assert [s["speaker"] for s in result["segments"]] == ["speaker_0", "speaker_1"]
    assert [w["word"] for s in result["segments"] for w in s["words"]] == ["hello", "yes"]
    assert calls == [("call.wav", "auto")]


def test_failed_forced_mlx_alignment_is_not_reported_as_native_timing(monkeypatch, tmp_path):
    import json
    import numpy as np
    from types import SimpleNamespace
    import asr_mlx
    import diarize_nemotron as dn
    def failed_alignment(**kwargs):
        raise RuntimeError("No aligner for this language")
    def asr(*args, **kwargs):
        assert kwargs["word_timestamps"] is False
        return {"language": "en", "segments": [{"text": "Hello world.", "start": 0., "end": 1.}]}
    monkeypatch.setattr(asr_mlx, "transcribe", asr)
    monkeypatch.setattr(dn, "select_backend", lambda *a, **kw: "pyannote")
    monkeypatch.setitem(sys.modules, "whisperx", SimpleNamespace(
        load_audio=lambda path: np.zeros(16000), load_align_model=failed_alignment))
    core = SimpleNamespace(clear_cache=lambda: None)
    holder = SimpleNamespace(model="cached")
    monkeypatch.setitem(sys.modules, "mlx", SimpleNamespace(core=core))
    monkeypatch.setitem(sys.modules, "mlx.core", core)
    monkeypatch.setitem(sys.modules, "mlx_whisper.transcribe", SimpleNamespace(ModelHolder=holder))
    output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["wrapper", "--audio", "call.wav", "--output", str(output),
                                     "--asr", "mlx", "--alignment", "forced"])
    assert tw.main() == 0
    result = json.loads(output.read_text())
    assert result["pipeline"]["alignment"] == "none"
    assert result["segments"][0]["text"] == "Hello world."
    assert not result["segments"][0].get("words")
    assert holder.model is None


def test_device_auto_picks_cuda_only_when_torch_sees_a_gpu():
    assert tw.resolve_device("auto", cuda_available=True) == "cuda"
    assert tw.resolve_device("auto", cuda_available=False) == "cpu"


def test_explicit_device_passes_through():
    for d in ("cpu", "cuda"):
        assert tw.resolve_device(d, cuda_available=False) == d
        assert tw.resolve_device(d, cuda_available=True) == d


def test_transcribe_sh_rejects_unknown_device_before_bootstrap(tmp_path):
    # Validation runs before `bootstrap`, so this needs no venv or models.
    import subprocess
    media = tmp_path / "m.wav"; media.write_bytes(b"")
    r = subprocess.run(["bash", str(HERE.parent / "scripts" / "transcribe.sh"), str(media), "--device", "gpu"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2
    assert "invalid --device: gpu" in r.stderr
