import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import diarize_reconcile as dr


def W(word, start, end, speaker):
    return {"word": word, "start": start, "end": end, "speaker": speaker}


def test_split_segment_on_speaker_change():
    seg = {"start": 0.0, "end": 4.0, "text": "hello there bob yes",
           "words": [W("hello", 0.0, 0.5, "SPEAKER_00"),
                     W("there", 0.6, 1.0, "SPEAKER_00"),
                     W("bob", 2.0, 2.4, "SPEAKER_01"),
                     W("yes", 2.5, 3.0, "SPEAKER_01")]}
    out = dr.split_segment_by_speaker(seg)
    assert len(out) == 2
    assert out[0]["speaker"] == "SPEAKER_00" and out[0]["text"] == "hello there"
    assert out[0]["start"] == 0.0 and out[0]["end"] == 1.0
    assert out[1]["speaker"] == "SPEAKER_01" and out[1]["text"] == "bob yes"
    assert out[1]["start"] == 2.0 and out[1]["end"] == 3.0


def test_smooth_single_word_blip():
    words = [W("a", 0.0, 0.4, "SPEAKER_00"),
             W("b", 0.5, 0.7, "SPEAKER_01"),   # lone blip, dur 0.2s
             W("c", 0.8, 1.2, "SPEAKER_00")]
    smoothed = dr.smooth_blips(words, min_blip_sec=0.4)
    assert [w["speaker"] for w in smoothed] == ["SPEAKER_00"] * 3


def test_blip_kept_when_long_enough():
    words = [W("a", 0.0, 0.4, "SPEAKER_00"),
             W("b", 0.5, 1.5, "SPEAKER_01"),   # 1.0s — a real short turn
             W("c", 1.6, 2.0, "SPEAKER_00")]
    smoothed = dr.smooth_blips(words, min_blip_sec=0.4)
    assert [w["speaker"] for w in smoothed] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]


def test_segment_without_word_speakers_passes_through():
    seg = {"start": 0.0, "end": 2.0, "text": "no speakers", "words": [{"word": "x"}]}
    out = dr.split_segment_by_speaker(seg)
    assert len(out) == 1 and out[0]["text"] == "no speakers"


def test_reconcile_full_result():
    result = {"language": "en", "segments": [
        {"start": 0.0, "end": 3.0, "text": "hi bob",
         "words": [W("hi", 0.0, 0.5, "SPEAKER_00"), W("bob", 2.0, 2.5, "SPEAKER_01")]}]}
    out = dr.reconcile(result)
    assert len(out["segments"]) == 2
    assert out["language"] == "en"


def test_word_with_speaker_but_no_end_does_not_crash():
    # whisperX assigns a speaker to unalignable tokens (e.g. numbers) that carry
    # start but NO end key. Such a word must not crash and the emitted segment
    # must carry a sane numeric end (>= start), since downstream does end - start.
    seg = {"start": 0.0, "end": 1.0, "text": "born 1995",
           "words": [W("born", 0.0, 0.3, "SPEAKER_00"),
                     {"word": "1995", "start": 0.4, "speaker": "SPEAKER_00"}]}
    out = dr.split_segment_by_speaker(seg)
    assert len(out) == 1
    end = out[0]["end"]
    assert isinstance(end, float)
    assert end >= out[0]["start"]


def test_blip_kept_when_duration_equals_threshold():
    # Strict-< semantics: a blip whose duration is exactly min_blip_sec is KEPT.
    words = [W("a", 0.0, 0.4, "SPEAKER_00"),
             W("b", 0.5, 0.9, "SPEAKER_01"),   # 0.4s == min_blip_sec
             W("c", 1.0, 1.4, "SPEAKER_00")]
    smoothed = dr.smooth_blips(words, min_blip_sec=0.4)
    assert [w["speaker"] for w in smoothed] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]
