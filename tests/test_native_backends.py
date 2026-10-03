import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import asr_mlx
import diarize_nemotron as dn
import diarize_reconcile as dr
import asr_gigaam3 as ga
import transcript_confidence as tc
import eta_helper


def test_rttm_preserves_overlap_and_nonconsecutive_labels():
    raw = """SPEAKER call 1 2.0 1.0 <NA> <NA> speaker_7 <NA> <NA>
SPEAKER call 1 1.0 2.0 <NA> <NA> speaker_2 <NA> <NA>
"""
    assert dn.parse_rttm(raw) == [(1.0, 3.0, "speaker_2"), (2.0, 3.0, "speaker_7")]


@pytest.mark.parametrize("raw", ["SPEAKER x", "SPEAKER x 1 nan 2 x x A",
                                "SPEAKER x 1 -1 2 x x A", "SPEAKER x 1 1 0 x x A"])
def test_invalid_diarization_does_not_publish_a_plausible_transcript(raw):
    with pytest.raises(ValueError):
        dn.parse_rttm(raw)


def test_missing_explicit_runtime_is_actionable(monkeypatch):
    monkeypatch.setenv("SCRIBA_NEMO_BIN", "/nonexistent/nemo-speech")
    with pytest.raises(FileNotFoundError, match="SCRIBA_NEMO_BIN"):
        dn.executable()


def test_auto_diarization_falls_back_only_when_runtime_is_missing(monkeypatch):
    monkeypatch.setattr(dn, "executable", lambda: None)
    assert dn.select_backend() == "pyannote"
    with pytest.raises(FileNotFoundError, match="nemo-speech"):
        dn.select_backend("nemotron")
    monkeypatch.setattr(dn, "executable", lambda: "/native/nemo-speech")
    assert dn.select_backend() == "nemotron"
    assert dn.select_backend("pyannote") == "pyannote"


@pytest.mark.parametrize("controls", [{"num_speakers": 2}, {"num_speakers": 9},
                                     {"enroll": "Alice=alice.wav"}])
def test_speaker_controls_use_pyannote_even_with_native_runtime(monkeypatch, controls):
    monkeypatch.setattr(dn, "executable", lambda: "/native/nemo-speech")
    assert dn.select_backend(**controls) == "pyannote"
    with pytest.raises(ValueError, match="--diarizer pyannote"):
        dn.select_backend("nemotron", **controls)


def test_invalid_explicit_runtime_does_not_silently_change_models(monkeypatch):
    monkeypatch.setenv("SCRIBA_NEMO_BIN", "/nonexistent/nemo-speech")
    with pytest.raises(FileNotFoundError):
        dn.select_backend()


def test_native_device_mapping_and_no_language_argument(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(dn, "executable", lambda: "/native/nemo-speech")
    captured = []
    def run(command, **kwargs):
        captured.append(command)
        return SimpleNamespace(stdout="SPEAKER x 1 0.0 1.0 x x A\n")
    monkeypatch.setattr(dn.subprocess, "run", run)
    assert dn.diarize("/audio/Deutsch call.wav", "mps") == [(0., 1., "A")]
    assert captured[0][2] == "/audio/Deutsch call.wav"
    assert captured[0][captured[0].index("--device") + 1] == "metal"
    assert "--language" not in captured[0]


def test_mlx_uses_multilingual_weights_and_preserves_custom_repo():
    assert asr_mlx.model_repo("large-v3-turbo") == "mlx-community/whisper-large-v3-turbo"
    assert asr_mlx.model_repo("large-v3") == "mlx-community/whisper-large-v3-mlx"
    assert asr_mlx.model_repo("my/model") == "my/model"


def test_unaligned_numbers_and_leading_words_survive_speaker_split():
    words = [{"word": "50"}, {"word": "миллионов", "start": 0., "end": 1., "speaker": "A"},
             {"word": "рублей"}, {"word": "да", "start": 1.1, "end": 1.3, "speaker": "B"}]
    out = dr.split_segment_by_speaker({"words": words}, min_blip_sec=0)
    assert [s["text"] for s in out] == ["50 миллионов рублей", "да"]
    assert [w["word"] for s in out for w in s["words"]] == [w["word"] for w in words]


def test_a_short_russian_reply_can_keep_its_speaker():
    words = [{"word": "вопрос", "start": 0., "end": 1., "speaker": "A"},
             {"word": "да", "start": 1.1, "end": 1.3, "speaker": "B"},
             {"word": "дальше", "start": 1.4, "end": 2., "speaker": "A"}]
    out = dr.split_segment_by_speaker({"words": words}, min_blip_sec=0)
    assert [s["speaker"] for s in out] == ["A", "B", "A"]


def test_gigaam_chunk_words_keep_absolute_time_and_punctuation():
    from types import SimpleNamespace
    result = SimpleNamespace(text="Да, 50 миллионов.", words=[
        SimpleNamespace(text="Да,", start=.1, end=.3),
        SimpleNamespace(text="50", start=.4, end=.6)])
    seg = ga.normalize_segment(result, 80, 83)
    assert seg["text"] == "Да, 50 миллионов."
    assert seg["words"][0] == {"word": "Да,", "start": 80.1, "end": 80.3}
    assert seg["words"][1]["start"] == 80.4


def test_unknown_asr_confidence_is_not_reported_as_perfect():
    segs, pct = tc.enrich_segments([{"words": [{"word": "да", "start": 0., "end": .2}]}], [])
    assert segs[0]["words"][0]["asr_conf"] is None
    assert pct == 0


def test_calibration_does_not_mix_fast_and_slow_diarizers(tmp_path):
    cache = str(tmp_path / "calibration.json")
    native = "gigaam-v3-rnnt-int8:gigaam:nemotron:auto:forced"
    pyannote = "gigaam-v3-rnnt-int8:gigaam:pyannote:cpu:forced"
    eta_helper.record("cpu", native, 300, 30, cache)
    eta_helper.record("cpu", pyannote, 300, 150, cache)
    assert eta_helper.get_factor("cpu", native, "Apple M4 Max", cache)[0] == .1
    assert eta_helper.get_factor("cpu", pyannote, "Apple M4 Max", cache)[0] == .5
