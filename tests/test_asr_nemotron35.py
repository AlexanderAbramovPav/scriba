import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import asr_nemotron35 as nt
import eta_helper
import transcript_confidence as tc


def native(*words):
    return {"languages": ["de"], "words": [
        {"word": w, "start": s, "end": e, "confidence": 0, "speaker": spk} for w, s, e, spk in words]}


def test_speaker_zero_survives_and_labels_are_strings():
    segs = nt.to_segments(native(("Guten", 0., .4, 0), ("Morgen.", .4, .9, 0), ("Hallo", 1., 1.3, 1)))
    assert [s["speaker"] for s in segs] == ["speaker_0", "speaker_1"]
    assert segs[0]["words"][0]["speaker"] == "speaker_0"


def test_segments_split_at_speaker_change_pause_and_sentence_end():
    segs = nt.to_segments(native(
        ("Guten", 0., .4, 0), ("Morgen", .4, .9, 0), ("zusammen.", .9, 1.4, 0),
        ("Heute", 1.5, 1.8, 0), ("prüfen", 3.5, 3.9, 0), ("Ja,", 4.0, 4.2, 1), ("genau.", 4.2, 4.6, 1)))
    assert [s["text"] for s in segs] == ["Guten Morgen zusammen.", "Heute", "prüfen", "Ja, genau."]
    assert (segs[0]["start"], segs[0]["end"]) == (0., 1.4)


def test_placeholder_confidence_is_not_passed_on():
    segs = nt.to_segments(native(("da", 0., .2, 0)))
    assert "confidence" not in segs[0]["words"][0]
    enriched, _ = tc.enrich_segments(segs, [])
    assert enriched[0]["words"][0]["asr_conf"] is None


def test_words_without_speaker_tags_stay_unlabeled():
    segs = nt.to_segments({"words": [{"word": "hello", "start": 0, "end": .3}]})
    assert "speaker" not in segs[0] and "speaker" not in segs[0]["words"][0]


@pytest.mark.parametrize("start,end", [(float("nan"), 1.), (-1., 1.), (2., 1.)])
def test_invalid_word_timing_is_rejected(start, end):
    with pytest.raises(ValueError):
        nt.to_segments({"words": [{"word": "x", "start": start, "end": end}]})


def test_speaker_turns_merge_contiguous_runs():
    segs = nt.to_segments(native(("a.", 0., 1., 0), ("b.", 1., 2., 0), ("c.", 2., 3., 1)))
    assert nt.speaker_turns(segs) == [(0., 2., "speaker_0"), (2., 3., "speaker_1")]


def test_one_hour_limit_is_actionable():
    nt.check_duration(3600)
    with pytest.raises(ValueError, match="60 minutes"):
        nt.check_duration(3601)


def test_salm_probe():
    assert nt.supports_salm("  --instruction TEXT   Speech-LLM: instruction")
    assert not nt.supports_salm("Usage: nemo-speech transcribe INPUT [--model MODEL]")


def test_command_with_language_glossary_and_speakers(monkeypatch):
    monkeypatch.delenv("SCRIBA_NEMOTRON35_INSTRUCTION", raising=False)
    cmd = nt.build_command("/bin/ns", "/a.wav", "/m.gguf", "/o.json", language="de", glossary="Grafana, Ozon")
    assert cmd[:3] == ["/bin/ns", "transcribe", "/a.wav"]
    for flag in ("--word-times", "--diarize", "--force"):
        assert flag in cmd
    assert cmd[cmd.index("--format") + 1] == "json"
    assert cmd[cmd.index("-l") + 1] == "de"
    prompt = cmd[cmd.index("--instruction") + 1]
    assert prompt.startswith("Transcribe this German audio with punctuation")
    assert prompt.endswith("Possible terms: Grafana, Ozon.")


def test_command_without_language_or_diarization(monkeypatch):
    monkeypatch.delenv("SCRIBA_NEMOTRON35_INSTRUCTION", raising=False)
    cmd = nt.build_command("/bin/ns", "/a.wav", "/m.gguf", "/o.json", diarize=False)
    assert "-l" not in cmd and "--diarize" not in cmd
    prompt = cmd[cmd.index("--instruction") + 1]
    assert prompt.startswith("Transcribe this audio with") and "<spk:" not in prompt


def test_speaker_prompt_is_the_measured_one(monkeypatch):
    monkeypatch.delenv("SCRIBA_NEMOTRON35_INSTRUCTION", raising=False)
    assert nt.instruction("en") == (
        "Transcribe this English audio with punctuation and capitalization. Include all spoken "
        "words and verbal fillers. Write numbers in their standard written form. Put speaker "
        "tags <spk:0> <spk:1> <spk:2> <spk:3> on the transcription.")


def test_instruction_override(monkeypatch):
    monkeypatch.setenv("SCRIBA_NEMOTRON35_INSTRUCTION", "Transcribe {language}speech.")
    assert nt.instruction("en") == "Transcribe English speech."


@pytest.mark.parametrize("controls,expected", [
    ({}, True), ({"diarizer": "nemotron"}, True), ({"diarizer": "pyannote"}, False),
    ({"num_speakers": 3}, False), ({"enroll": "Alice=a.wav"}, False)])
def test_embedded_speakers_yield_to_pyannote_controls(controls, expected):
    assert nt.embedded_speakers(**controls) is expected


def test_runtime_and_model_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRIBA_NEMOTRON35_BIN", "/nonexistent/nemo-speech")
    with pytest.raises(FileNotFoundError, match="SCRIBA_NEMOTRON35_BIN"):
        nt.executable()
    binary = tmp_path / "nemo-speech"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("SCRIBA_NEMOTRON35_BIN", str(binary))
    assert nt.executable() == str(binary)
    monkeypatch.setenv("SCRIBA_NEMOTRON35_MODEL", str(tmp_path / "m.gguf"))
    assert nt.model_path() == tmp_path / "m.gguf"
    assert nt.model_path("/x/y.gguf") == pathlib.Path("/x/y.gguf")


def test_eta_has_its_own_initial_factor_and_calibration(tmp_path):
    cache = str(tmp_path / "calibration.json")
    profile = "NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-AD-IQ4_NL:nemotron35:nemotron:auto:forced"
    assert eta_helper.get_factor("metal", profile, "Apple M4 Max", cache) == (.3, "chip_default", "Nemotron 3.5 (Metal)")
    eta_helper.record("metal", profile, 600, 120, cache)
    assert eta_helper.get_factor("metal", profile, "Apple M4 Max", cache)[:2] == (.2, "calibrated")
