import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import transcript_confidence as tc


def test_overlap_regions_basic():
    turns = [(0.0, 2.0, "A"), (1.0, 3.0, "B")]   # overlap 1-2
    assert tc.overlap_regions(turns) == [(1.0, 2.0)]


def test_overlap_regions_none():
    turns = [(0.0, 1.0, "A"), (1.0, 2.0, "B")]
    assert tc.overlap_regions(turns) == []


def test_word_in_overlap():
    regions = [(1.0, 2.0)]
    assert tc.word_in_overlap(1.2, 1.6, regions) is True
    assert tc.word_in_overlap(2.1, 2.4, regions) is False


def test_speaker_confidence_clean():
    turns = [(0.0, 2.0, "A"), (3.0, 4.0, "B")]
    assert tc.speaker_confidence(0.2, 0.8, "A", turns) == 1.0


def test_speaker_confidence_contested():
    turns = [(0.0, 1.5, "A"), (1.5, 3.0, "B")]
    m = tc.speaker_confidence(1.0, 2.0, "A", turns)
    assert 0.0 <= m <= 0.2


def test_enrich_segments_adds_fields_and_pct():
    segments = [{"start": 0.0, "end": 1.0, "speaker": "A", "text": "hi",
                 "words": [{"word": "hi", "start": 0.0, "end": 1.0, "score": 0.9, "speaker": "A"}]}]
    turns = [(0.0, 1.0, "A")]
    enriched, low_pct = tc.enrich_segments(segments, turns)
    w = enriched[0]["words"][0]
    assert w["asr_conf"] == 0.9 and w["overlap"] is False and w["speaker_conf"] == 1.0
    assert "flags" in enriched[0]
    assert low_pct == 0.0


def test_enrich_no_turns_not_all_flagged():
    # Diarization off / single-speaker: no turns to confirm attribution. Good ASR
    # score, no overlap → nothing should be flagged just because turns are empty.
    segments = [{"start": 0.0, "end": 1.0, "speaker": "A", "text": "hi",
                 "words": [{"word": "hi", "start": 0.0, "end": 1.0, "score": 0.9, "speaker": "A"}]}]
    enriched, low_pct = tc.enrich_segments(segments, [])
    for seg in enriched:
        assert seg["flags"]["shaky_attribution"] is False
        for w in seg["words"]:
            assert w["speaker_conf"] == 1.0
    assert low_pct == 0.0


def test_enrich_numpy_inputs_are_json_native():
    # whisperX/pyannote feed NumPy scalars; our computed fields must come out as
    # native Python types, and the whole sidecar must json-serialize. Regression
    # for "TypeError: Object of type bool is not JSON serializable" (real-run bug).
    try:
        import numpy as np
    except ImportError:
        return
    import json, pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    import jsonsafe
    segments = [{"start": 0.0, "end": 1.0, "speaker": "A", "text": "hi",
                 "words": [{"word": "hi", "start": np.float64(0.2), "end": np.float64(0.8),
                            "score": np.float32(0.9), "speaker": "A"}]}]
    turns = [(np.float64(0.0), np.float64(1.0), "A"), (np.float64(0.5), np.float64(1.5), "B")]
    enriched, low = tc.enrich_segments(segments, turns)
    w = enriched[0]["words"][0]
    assert type(w["overlap"]) is bool
    assert type(w["speaker_conf"]) is float
    assert type(enriched[0]["flags"]["overlap"]) is bool
    assert type(enriched[0]["flags"]["shaky_attribution"]) is bool
    json.dumps({"segments": enriched, "low": low}, default=jsonsafe.json_default)


def test_zero_width_word_not_flagged():
    # C1 manufactures end==start words for unalignable tokens (e.g. numbers). A
    # zero-width interval can't overlap any turn, so speaker_confidence must treat
    # it as not-assessable (1.0) rather than 0.0 — else low_confidence_pct inflates.
    turns = [(0.0, 5.0, "A")]
    assert tc.speaker_confidence(0.4, 0.4, "A", turns) == 1.0
    segments = [{"start": 0.0, "end": 1.0, "speaker": "A", "text": "in 1995",
                 "words": [{"word": "in", "start": 0.0, "end": 0.3, "score": 0.9, "speaker": "A"},
                           {"word": "1995", "start": 0.4, "end": 0.4, "score": 0.9, "speaker": "A"}]}]
    enriched, low = tc.enrich_segments(segments, turns)
    assert enriched[0]["flags"]["shaky_attribution"] is False
    assert low == 0.0
