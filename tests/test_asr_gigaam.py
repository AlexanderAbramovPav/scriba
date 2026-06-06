import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import asr_gigaam as ga


def test_normalize_with_token_timestamps():
    raw = {"text": "привет мир", "tokens": ["привет", "мир"],
           "timestamps": [0.0, 0.6], "durations": [0.5, 0.4]}
    out = ga.normalize_segments(raw)
    seg = out["segments"][0]
    assert seg["text"] == "привет мир"
    assert seg["words"][0] == {"word": "привет", "start": 0.0, "end": 0.5, "score": 1.0}
    assert seg["words"][1]["start"] == 0.6
    assert out["needs_alignment"] is False


def test_normalize_without_timestamps_marks_fallback():
    raw = {"text": "привет мир", "tokens": [], "timestamps": []}
    out = ga.normalize_segments(raw)
    assert out["needs_alignment"] is True
    assert out["segments"][0]["text"] == "привет мир"


def test_chars_to_words_groups_on_space():
    # GigaAM emits character tokens with a literal space separator.
    tokens = ["н", "е", " ", "д", "а"]
    ts = [0.0, 0.1, 0.2, 0.3, 0.4]
    durs = [0.05, 0.05, 0.0, 0.05, 0.05]
    words = ga.chars_to_words(tokens, ts, durs)
    assert words == [
        {"word": "не", "start": 0.0, "end": 0.15, "score": 1.0},
        {"word": "да", "start": 0.3, "end": 0.45, "score": 1.0},
    ]


def test_normalize_char_level_groups_words():
    raw = {"text": "не да", "tokens": ["н", "е", " ", "д", "а"],
           "timestamps": [0.0, 0.1, 0.2, 0.3, 0.4],
           "durations": [0.05, 0.05, 0.0, 0.05, 0.05]}
    out = ga.normalize_segments(raw)
    assert out["needs_alignment"] is False
    seg = out["segments"][0]
    assert [w["word"] for w in seg["words"]] == ["не", "да"]
    assert seg["start"] == 0.0 and seg["end"] == 0.45
    assert seg["text"] == "не да"
