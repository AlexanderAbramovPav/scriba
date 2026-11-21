import errno
import json
import os
import pathlib
import stat
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


def _run_cli(*args):
    return subprocess.run([sys.executable, str(pathlib.Path(ui.__file__)), *args],
                          capture_output=True, text=True)


def test_upsert_refuses_dangling_symlink(tmp_path):
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    link = scriba / "index.json"
    link.symlink_to(tmp_path / "unmounted" / "index.json")
    with pytest.raises(ui.IndexReadError, match="does not exist"):
        ui.upsert(scriba, _entry("new"))
    assert link.is_symlink() and not link.exists()
    assert not list(scriba.glob("*.tmp"))


def test_upsert_writes_through_valid_symlink(tmp_path):
    real_dir = tmp_path / "synced"
    real_dir.mkdir()
    real = real_dir / "index.json"
    real.write_text(json.dumps({"schema_version": 1, "recordings": [_entry("a")]}))
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    (scriba / "index.json").symlink_to(real)
    ui.upsert(scriba, _entry("b"))
    assert (scriba / "index.json").is_symlink()
    ids = [r["id"] for r in json.loads(real.read_text())["recordings"]]
    assert sorted(ids) == ["a", "b"]


def test_upsert_tolerates_non_string_dates(tmp_path):
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    (scriba / "index.json").write_text(json.dumps(
        {"recordings": [{"id": "a", "date": None}, {"id": "b", "date": 5}]}))
    ui.upsert(scriba, _entry("c"))
    ids = {r["id"] for r in json.loads((scriba / "index.json").read_text())["recordings"]}
    assert ids == {"a", "b", "c"}


def test_upsert_keeps_existing_file_mode(tmp_path):
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("a"))
    idx = scriba / "index.json"
    os.chmod(idx, 0o644)
    ui.upsert(scriba, _entry("b"))
    assert stat.S_IMODE(idx.stat().st_mode) == 0o644


def test_new_index_mode_follows_umask(tmp_path):
    old = os.umask(0o022)
    try:
        ui.upsert(tmp_path / ".scriba", _entry("a"))
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / ".scriba" / "index.json").stat().st_mode) == 0o644


def test_upsert_ignores_unsupported_fsync(tmp_path, monkeypatch):
    def no_fsync(fd):
        raise OSError(errno.EINVAL, "Invalid argument")

    monkeypatch.setattr(ui.os, "fsync", no_fsync)
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("a"))
    assert json.loads((scriba / "index.json").read_text())["recordings"][0]["id"] == "a"


def test_cli_reports_other_errors_without_traceback(tmp_path):
    scriba = tmp_path / ".scriba"
    res = _run_cli("upsert", str(scriba), "{not json")
    assert res.returncode == 1 and "scriba: index not updated" in res.stderr
    assert "Traceback" not in res.stderr
    res = _run_cli("upsert", str(scriba), json.dumps({"title": "no id"}))
    assert res.returncode == 1 and "string 'id'" in res.stderr
    assert "Traceback" not in res.stderr


def test_upsert_refuses_index_it_cannot_stat(tmp_path, monkeypatch):
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("a"))
    original = (scriba / "index.json").read_bytes()
    real_lstat = os.lstat

    def flaky_lstat(path, *a, **kw):
        if str(path).endswith("index.json"):
            raise OSError(errno.EIO, "Input/output error")
        return real_lstat(path, *a, **kw)

    monkeypatch.setattr(ui.os, "lstat", flaky_lstat)
    with pytest.raises(ui.IndexReadError, match="cannot access"):
        ui.upsert(scriba, _entry("b"))
    _assert_untouched(scriba, original)


def test_upsert_refuses_directory_named_index(tmp_path):
    scriba = tmp_path / ".scriba"
    (scriba / "index.json").mkdir(parents=True)
    with pytest.raises(ui.IndexReadError, match="not a regular file"):
        ui.upsert(scriba, _entry("a"))


def test_upsert_creates_missing_symlink_target(tmp_path):
    synced = tmp_path / "synced"
    synced.mkdir()
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    (scriba / "index.json").symlink_to(synced / "index.json")
    ui.upsert(scriba, _entry("a"))
    assert (scriba / "index.json").is_symlink()
    assert json.loads((synced / "index.json").read_text())["recordings"][0]["id"] == "a"


def test_upsert_refuses_symlink_loop(tmp_path):
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    (scriba / "index.json").symlink_to(scriba / "index.json")
    with pytest.raises(ui.IndexReadError):
        ui.upsert(scriba, _entry("a"))
    assert (scriba / "index.json").is_symlink()


def test_upsert_refuses_too_deep_index(tmp_path):
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    deep = b"[" * 100000 + b"]" * 100000
    (scriba / "index.json").write_bytes(deep)
    with pytest.raises(ui.IndexReadError):
        ui.upsert(scriba, _entry("a"))
    _assert_untouched(scriba, deep)


@pytest.mark.parametrize("code", [errno.ENOTSUP, errno.ENOSYS])
def test_upsert_ignores_other_unsupported_fsync(tmp_path, monkeypatch, code):
    def no_fsync(fd):
        raise OSError(code, "not supported")

    monkeypatch.setattr(ui.os, "fsync", no_fsync)
    ui.upsert(tmp_path / ".scriba", _entry("a"))
    assert (tmp_path / ".scriba" / "index.json").exists()


def test_upsert_fsync_io_error_still_fails(tmp_path, monkeypatch):
    def bad_fsync(fd):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(ui.os, "fsync", bad_fsync)
    scriba = tmp_path / ".scriba"
    with pytest.raises(OSError):
        ui.upsert(scriba, _entry("a"))
    assert not (scriba / "index.json").exists()
    assert not list(scriba.glob("*.tmp"))


@pytest.mark.parametrize("args", [(), ("upsert",), ("upsert", "x"), ("upser", "x", "{}")])
def test_cli_bad_arguments_exit_2(args):
    res = _run_cli(*args)
    assert res.returncode == 2
    assert "usage:" in res.stderr and "Traceback" not in res.stderr
