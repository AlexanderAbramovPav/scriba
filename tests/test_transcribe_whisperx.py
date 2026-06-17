import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
# Imports cleanly without the ML stack: `import whisperx` is deferred into main(), and CI installs
# only pytest+numpy. This guards the regression in issue #3 (diarization died on pyannote 3.x).
import transcribe_whisperx as tw


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
