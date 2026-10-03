import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import punctuate


@pytest.mark.parametrize("raw,edited", [
    ("да да ну я думаю хорошо", "Да, да, ну, я думаю, хорошо."),
    ("цена 1,5 рубля скидка 50%", "Цена — 1,5 рубля, скидка — 50%."),
    ("по-русски hello don't", "По-русски: Hello, don't!"),
])
def test_punctuation_and_case_only(raw, edited):
    punctuate.validate_edit(raw, edited)


@pytest.mark.parametrize("raw,edited", [
    ("да да ну", "Да, ну."),
    ("да нет", "Нет, да."),
    ("сена", "Селена."),
    ("16 долгов", "16 долларов."),
    ("50%", "50."),
    ("1,5", "1.5"),
    ("5", "-5"),
    ("из за", "Из-за."),
    ("a + b", "+ a b."),
    ("a", "a\u0301"),
    ("да", "Да 😊"),
])
def test_reject_content_changes(raw, edited):
    with pytest.raises(ValueError):
        punctuate.validate_edit(raw, edited)


@pytest.fixture
def source(tmp_path):
    p = tmp_path / "transcript.json"
    p.write_text(json.dumps({"language": "ru", "segments": [
        {"text": "да да", "speaker": "A", "start": 1, "end": 2,
         "words": [{"word": "да", "start": 1, "score": None}]},
        {"text": "нет", "speaker": "B", "start": 2, "end": 3}],
        "diarization_turns": [{"start": 1, "end": 2, "speaker": "A"}]}))
    return p


def edits_for(source):
    ex = punctuate.export(source)
    return {"source_sha256": ex["source_sha256"], "segments": [
        {"id": 0, "text": "Да, да."}, {"id": 1, "text": "Нет!"}]}


def test_preserves_source_and_all_speaker_timing_evidence(source):
    original = source.read_bytes()
    before = json.loads(original)
    result = punctuate.apply(source, edits_for(source))
    assert source.read_bytes() == original
    assert result["diarization_turns"] == before["diarization_turns"]
    for a, b in zip(before["segments"], result["segments"]):
        assert b["raw_text"] == a["text"]
        assert {k: v for k, v in a.items() if k != "text"} == {
            k: v for k, v in b.items() if k not in {"text", "raw_text"}}


@pytest.mark.parametrize("kind", ["missing", "duplicate", "metadata", "stale"])
def test_bad_patch_rejected(source, kind):
    edits = edits_for(source)
    if kind == "missing":
        edits["segments"].pop()
    elif kind == "duplicate":
        edits["segments"][1]["id"] = 0
    elif kind == "metadata":
        edits["segments"][0]["speaker"] = "B"
    else:
        edits["source_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        punctuate.apply(source, edits)


def test_renderer_reuses_clips_and_points_to_punctuated_sidecar(source, tmp_path):
    output = tmp_path / "transcript.punctuated.json"
    output.write_text(json.dumps(punctuate.apply(source, edits_for(source))))
    clips = tmp_path / "data"
    clips.mkdir()
    clip = clips / "speaker-1.wav"
    clip.write_bytes(b"existing voice evidence")
    renderer = pathlib.Path(punctuate.__file__).with_name("json_to_md.py")
    result = subprocess.run([sys.executable, str(renderer), str(output),
                             "--source", "call.wav", "--data-file", output.name,
                             "--reuse-clips", "--media-dir", str(clips)],
                            check=True, capture_output=True, text=True)
    assert "data: data/transcript.punctuated.json" in result.stdout
    assert "Да, да." in result.stdout
    assert 'src="data/speaker-1.wav"' in result.stdout
    assert clip.read_bytes() == b"existing voice evidence"
