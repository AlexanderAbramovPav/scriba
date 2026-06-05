import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import naming


def test_kebab():
    assert naming.kebab("Q3 Planning Sync!") == "q3-planning-sync"
    assert naming.kebab("  Привет Мир  ") == "привет-мир"
    assert naming.kebab("a__b--c") == "a-b-c"


def test_is_generic():
    for g in ["zoom_0", "GMT20260605-120000", "recording", "video", "audio",
              "2026-06-05", "rep", "新"]:
        assert naming.is_generic(g), g
    for ok in ["q3-planning-sync", "client-mp-kickoff", "weekly-standup"]:
        assert not naming.is_generic(ok), ok


def test_output_name_uses_title_override():
    assert naming.output_stem("zoom_0", title="Q3 Planning") == "q3-planning"


def test_output_name_falls_back_to_input_when_meaningful():
    assert naming.output_stem("Weekly Standup", title=None) == "weekly-standup"


def test_output_stem_empty_falls_back():
    assert naming.output_stem("!!!", None) == "transcript"
    assert naming.output_stem("   ", None) == "transcript"
