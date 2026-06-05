import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
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
    deep = tmp_path / "a" / "b"; deep.mkdir(parents=True)
    assert ui.find_index_dir(deep) == tmp_path / ".scriba"
