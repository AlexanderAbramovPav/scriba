import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import enroll


def test_cosine():
    assert abs(enroll.cosine([1, 0], [1, 0]) - 1.0) < 1e-6
    assert abs(enroll.cosine([1, 0], [0, 1]) - 0.0) < 1e-6


def test_match_above_threshold():
    clusters = {"SPEAKER_00": [1.0, 0.0], "SPEAKER_01": [0.0, 1.0]}
    refs = {"Alice": [0.99, 0.01], "Bob": [0.02, 0.98]}
    m = enroll.match_clusters(clusters, refs, threshold=0.8)
    assert m == {"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"}


def test_below_threshold_unmapped():
    clusters = {"SPEAKER_00": [1.0, 0.0]}
    refs = {"Alice": [0.0, 1.0]}
    assert enroll.match_clusters(clusters, refs, threshold=0.8) == {}


def test_ref_not_double_claimed():
    clusters = {"SPEAKER_00": [1.0, 0.0], "SPEAKER_01": [0.95, 0.05]}
    refs = {"Alice": [1.0, 0.0]}  # both clusters look like Alice
    m = enroll.match_clusters(clusters, refs, threshold=0.5)
    assert list(m.values()).count("Alice") == 1  # greedy: only the best cluster wins


def test_embeddings_to_dict_positional():
    labels = ["SPEAKER_00", "SPEAKER_01"]
    arr = [[1.0, 0.0], [0.0, 1.0]]
    d = enroll.embeddings_to_dict(labels, arr)
    assert d == {"SPEAKER_00": [1.0, 0.0], "SPEAKER_01": [0.0, 1.0]}


def test_embeddings_to_dict_none_and_mismatch():
    assert enroll.embeddings_to_dict(["A"], None) == {}
    # more labels than rows: extra labels skipped, no crash
    assert enroll.embeddings_to_dict(["A", "B"], [[1.0, 2.0]]) == {"A": [1.0, 2.0]}
