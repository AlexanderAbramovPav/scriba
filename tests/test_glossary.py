import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import glossary as g


def test_resolve_project_over_global(tmp_path, monkeypatch):
    proj = tmp_path / "rec"; proj.mkdir()
    (proj / ".scriba").mkdir()
    (proj / ".scriba" / "glossary.txt").write_text("GolOps\nPMEF\n", encoding="utf-8")
    home = tmp_path / "home"; (home / ".config" / "scriba").mkdir(parents=True)
    (home / ".config" / "scriba" / "glossary").write_text("PMEF\nNeMo\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    terms = g.resolve_glossary(proj)
    assert terms == ["GolOps", "PMEF", "NeMo"]   # project first, deduped, order kept


def test_resolve_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    assert g.resolve_glossary(tmp_path) == []


def test_build_prompt():
    assert g.build_prompt(["GolOps", "PMEF"]) == "GolOps, PMEF"
    assert g.build_prompt([]) == ""
