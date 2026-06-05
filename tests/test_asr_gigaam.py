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
