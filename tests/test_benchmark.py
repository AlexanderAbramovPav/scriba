import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_der as b


def test_der_identical_is_zero(tmp_path):
    rttm = ("SPEAKER f 1 0.000 2.000 <NA> <NA> A <NA> <NA>\n"
            "SPEAKER f 1 2.000 2.000 <NA> <NA> B <NA> <NA>\n")
    ref = tmp_path / "ref.rttm"
    ref.write_text(rttm)
    hyp = tmp_path / "hyp.rttm"
    hyp.write_text(rttm)
    assert b.der(str(ref), str(hyp)) == 0.0


def test_der_identical_relabeled_is_zero(tmp_path):
    # Same partition, different speaker NAMES -> optimal mapping makes DER 0.
    ref = tmp_path / "ref.rttm"
    ref.write_text("SPEAKER f 1 0.000 2.000 <NA> <NA> A <NA> <NA>\n"
                   "SPEAKER f 1 2.000 2.000 <NA> <NA> B <NA> <NA>\n")
    hyp = tmp_path / "hyp.rttm"
    hyp.write_text("SPEAKER f 1 0.000 2.000 <NA> <NA> X <NA> <NA>\n"
                   "SPEAKER f 1 2.000 2.000 <NA> <NA> Y <NA> <NA>\n")
    assert b.der(str(ref), str(hyp)) == 0.0


def test_der_mismatch_positive(tmp_path):
    ref = tmp_path / "ref.rttm"
    ref.write_text("SPEAKER f 1 0.000 4.000 <NA> <NA> A <NA> <NA>\n")
    hyp = tmp_path / "hyp.rttm"
    # extra speaker = false alarm/overlap
    hyp.write_text("SPEAKER f 1 0.000 4.000 <NA> <NA> A <NA> <NA>\n"
                   "SPEAKER f 1 1.000 1.000 <NA> <NA> B <NA> <NA>\n")
    assert b.der(str(ref), str(hyp)) > 0.0
