import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import update_index as ui


def test_upsert_creates_and_updates(tmp_path):
    scriba = tmp_path / ".scriba"
    e1 = {"id": "a", "title": "Sync", "date": "2026-06-05", "lang": "en",
          "duration": 600, "folder": "sync.transcript", "low_conf_pct": 3.0,
          "participants": ["Alice"], "keywords": ["pricing"]}
    ui.upsert(scriba, e1)
    idx = json.loads((scriba / "index.json").read_text())
    assert len(idx["recordings"]) == 1
    e1b = dict(e1, title="Sync v2")
    ui.upsert(scriba, e1b)
    idx = json.loads((scriba / "index.json").read_text())
    assert len(idx["recordings"]) == 1 and idx["recordings"][0]["title"] == "Sync v2"


def test_find_index_dir_walks_up(tmp_path):
    (tmp_path / ".scriba").mkdir()
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert ui.find_index_dir(deep) == tmp_path / ".scriba"


def _entry(id_, date="2026-06-05"):
    return {"id": id_, "title": id_, "date": date, "lang": "en", "duration": 60,
            "folder": f"{id_}.transcript", "low_conf_pct": 0.0}


def _assert_untouched(scriba, original):
    assert (scriba / "index.json").read_bytes() == original
    assert not list(scriba.glob("*.tmp"))


def test_upsert_keeps_other_entries(tmp_path):
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("a", "2026-06-05"))
    ui.upsert(scriba, _entry("b", "2026-06-01"))
    idx = json.loads((scriba / "index.json").read_text())
    assert [r["id"] for r in idx["recordings"]] == ["b", "a"]
    assert idx["schema_version"] == 1
    assert not list(scriba.glob("*.tmp"))


@pytest.mark.parametrize("content", [
    b'{"schema_version": 1, "recordings": [{"id": "a"',  # truncated JSON
    b"",  # empty file
    b"  \n",  # whitespace only
    b"\xff\xfe not utf-8",  # bad encoding
    b"[]",  # top level is not an object
    b'{"recordings": {"id": "a"}}',  # recordings is not a list
    b'{"recordings": ["a"]}',  # entry is not an object
])
def test_upsert_refuses_unreadable_index(tmp_path, content):
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    (scriba / "index.json").write_bytes(content)
    with pytest.raises(ui.IndexReadError) as exc:
        ui.upsert(scriba, _entry("new"))
    assert str(scriba / "index.json") in str(exc.value)
    _assert_untouched(scriba, content)


def test_upsert_write_failure_keeps_old_index(tmp_path, monkeypatch):
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("a"))
    original = (scriba / "index.json").read_bytes()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(ui.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        ui.upsert(scriba, _entry("b"))
    _assert_untouched(scriba, original)


def test_cli_reports_unreadable_index(tmp_path):
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    content = b'{"recordings": [{"id": "a"}'
    (scriba / "index.json").write_bytes(content)
    script = pathlib.Path(ui.__file__)
    res = subprocess.run(
        [sys.executable, str(script), "upsert", str(scriba), json.dumps(_entry("new"))],
        capture_output=True, text=True,
    )
    assert res.returncode == 1
    assert str(scriba / "index.json") in res.stderr
    assert "Traceback" not in res.stderr
    _assert_untouched(scriba, content)
