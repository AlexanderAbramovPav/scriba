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


@pytest.mark.parametrize("args", [
    (),
    ("upsert",),
    ("upsert", "x"),
    ("upser", "x", "{}"),
    ("record",),
    ("record", "x"),
    ("rebuild",),
])
def test_cli_bad_arguments_exit_2(args):
    res = _run_cli(*args)
    assert res.returncode == 2
    assert "usage:" in res.stderr and "Traceback" not in res.stderr


def test_upsert_tolerates_chmod_failure(tmp_path, monkeypatch):
    def no_chmod(path, mode):
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(ui.os, "chmod", no_chmod)
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("a"))
    assert json.loads((scriba / "index.json").read_text())["recordings"][0]["id"] == "a"
    assert not list(scriba.glob("*.tmp"))


def test_upsert_concurrent_processes(tmp_path):
    scriba = tmp_path / ".scriba"
    script = pathlib.Path(ui.__file__)
    count = 20
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                str(script),
                "upsert",
                str(scriba),
                json.dumps(_entry(f"rec-{i:02d}", f"2026-06-{(i % 28) + 1:02d}")),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(count)
    ]
    failures = []
    for p in procs:
        out, err = p.communicate(timeout=30)
        if p.returncode != 0:
            failures.append((p.returncode, out, err))
    assert not failures
    data = json.loads((scriba / "index.json").read_text(encoding="utf-8"))
    ids = {r["id"] for r in data["recordings"]}
    assert ids == {f"rec-{i:02d}" for i in range(count)}
    assert len(data["recordings"]) == count
    assert not list(scriba.glob("*.tmp"))


def test_upsert_and_rebuild_without_fcntl(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "fcntl", None)
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("a"))
    assert [r["id"] for r in json.loads((scriba / "index.json").read_text())["recordings"]] == ["a"]
    res = ui.rebuild(tmp_path)
    assert res["total"] == 1


def _legacy_build_entry(rec_id, title, date, duration, folder, json_path):
    """Exact behaviour of the old inline python3 -c builder in transcribe.sh."""
    try:
        d = json.load(open(json_path, encoding="utf-8"))
    except Exception:
        d = {}
    return {
        "id": rec_id,
        "title": title,
        "date": date,
        "lang": d.get("language", "auto"),
        "duration": int(duration),
        "folder": folder,
        "low_conf_pct": float(d.get("low_confidence_pct", 0)),
    }


def test_build_entry_matches_legacy_inline_builder(tmp_path):
    full_json = tmp_path / "full.json"
    full_json.write_text(json.dumps({"language": "ru", "low_confidence_pct": 3.5}),
                         encoding="utf-8")
    empty_json = tmp_path / "empty.json"
    empty_json.write_text("{}", encoding="utf-8")
    broken_json = tmp_path / "broken.json"
    broken_json.write_text("{not json", encoding="utf-8")
    missing_json = tmp_path / "missing.json"

    for jpath in (full_json, empty_json, broken_json, missing_json):
        got = ui.build_entry("sync-1", "sync", "2026-06-05", "125", "sync.transcript", jpath)
        exp = _legacy_build_entry("sync-1", "sync", "2026-06-05", "125", "sync.transcript", jpath)
        assert got == exp
        assert type(got["duration"]) is int
        assert type(got["low_conf_pct"]) is float

    assert ui.build_entry("sync-2", "sync", "2026-06-05", 0, "sync.transcript") == {
        "id": "sync-2",
        "title": "sync",
        "date": "2026-06-05",
        "lang": "auto",
        "duration": 0,
        "folder": "sync.transcript",
        "low_conf_pct": 0.0,
    }


def test_cli_record_builds_and_upserts(tmp_path):
    scriba = tmp_path / ".scriba"
    tr = tmp_path / "transcript.json"
    tr.write_text(json.dumps({"language": "de", "low_confidence_pct": 2.25}), encoding="utf-8")

    res = _run_cli(
        "record",
        str(scriba),
        "--id=standup-1717603200",
        "--title=standup",
        "--date=2026-06-05",
        "--duration=360",
        "--folder=standup.transcript",
        f"--json={tr}",
    )
    assert res.returncode == 0, res.stderr
    idx = json.loads((scriba / "index.json").read_text(encoding="utf-8"))
    assert idx["recordings"] == [{
        "id": "standup-1717603200",
        "title": "standup",
        "date": "2026-06-05",
        "lang": "de",
        "duration": 360,
        "folder": "standup.transcript",
        "low_conf_pct": 2.25,
    }]

    # Missing JSON falls back to defaults instead of failing.
    res2 = _run_cli(
        "record",
        str(scriba),
        "--id=second-1",
        "--title=second",
        "--date=2026-06-06",
        "--duration=60",
        "--folder=second.transcript",
        f"--json={tmp_path / 'nope.json'}",
    )
    assert res2.returncode == 0, res2.stderr
    idx2 = json.loads((scriba / "index.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in idx2["recordings"]}
    assert by_id["second-1"]["lang"] == "auto"
    assert by_id["second-1"]["low_conf_pct"] == 0.0

    # Refuses unreadable index.json without overwriting it.
    corrupt = b"{broken"
    (scriba / "index.json").write_bytes(corrupt)
    res3 = _run_cli(
        "record",
        str(scriba),
        "--id=third-1",
        "--title=third",
        "--date=2026-06-07",
        "--duration=10",
        "--folder=third.transcript",
    )
    assert res3.returncode == 1
    assert "Traceback" not in res3.stderr
    _assert_untouched(scriba, corrupt)


def _write_transcript(root, rel_dir, stem, content, *, filename=None):
    rec_dir = root / rel_dir
    rec_dir.mkdir(parents=True, exist_ok=True)
    path = rec_dir / (filename or f"{stem}.md")
    path.write_text(content, encoding="utf-8")
    return path


def test_rebuild_from_fixture_tree(tmp_path):
    # Standard full front matter + companion punctuated copy (should be ignored).
    _write_transcript(
        tmp_path,
        "alpha.transcript",
        "alpha",
        "---\n"
        "id: alpha-1717603200\n"
        "source: alpha.mp4\n"
        "date: 2026-06-05\n"
        "duration: 01:02:03\n"
        "language: ru\n"
        "low_confidence_pct: 4.2\n"
        "---\n\n# alpha\n",
    )
    _write_transcript(
        tmp_path,
        "alpha.transcript",
        "alpha",
        "---\nid: should-not-be-indexed\n---\n",
        filename="alpha.punctuated.md",
    )

    # Missing id and low_confidence_pct -> id falls back to stem, low_conf_pct -> 0.0.
    _write_transcript(
        tmp_path,
        "beta.transcript",
        "beta",
        "---\n"
        "date: 2026-06-01\n"
        "duration: 00:05:30\n"
        "language: en\n"
        "---\n\n# beta\n",
    )

    # Quoted values, inline comments, BOM, CRLF.
    _write_transcript(
        tmp_path,
        "gamma.transcript",
        "gamma",
        "\ufeff---\r\n"
        'id: "gamma-quoted"   # inline comment\r\n'
        "date: '2026-06-03'\r\n"
        'duration: "00:00:45"\r\n'
        "language: 'fr' # comment\r\n"
        "low_confidence_pct: 1.5 # pct\r\n"
        "---\r\n\r\n# gamma\r\n",
    )

    # Empty front matter block -> defaults.
    _write_transcript(tmp_path, "delta.transcript", "delta", "---\n---\n# delta\n")

    # Nested transcript below recordings_dir.
    _write_transcript(
        tmp_path,
        "2026/nested.transcript",
        "nested",
        "---\n"
        "id: nested-9\n"
        "date: 2026-06-04\n"
        "duration: 00:10:00\n"
        "language: es\n"
        "---\n",
    )

    # Missing front matter -> skipped without failing rebuild.
    _write_transcript(tmp_path, "no-fm.transcript", "no-fm", "# just a heading\n")

    # Empty .transcript dir and unrelated markdown -> ignored.
    (tmp_path / "empty.transcript").mkdir()
    (tmp_path / "notes.md").write_text("---\nid: ignored\n---\n", encoding="utf-8")

    res = _run_cli("rebuild", str(tmp_path))
    assert res.returncode == 0, res.stderr
    assert "skipped" in res.stderr and "no-fm.md" in res.stderr

    idx = json.loads((tmp_path / ".scriba" / "index.json").read_text(encoding="utf-8"))
    assert idx["schema_version"] == 1
    assert [r["id"] for r in idx["recordings"]] == [
        "delta",
        "beta",
        "gamma-quoted",
        "nested-9",
        "alpha-1717603200",
    ]
    by_id = {r["id"]: r for r in idx["recordings"]}
    assert by_id["alpha-1717603200"] == {
        "id": "alpha-1717603200",
        "title": "alpha",
        "date": "2026-06-05",
        "lang": "ru",
        "duration": 3723,
        "folder": "alpha.transcript",
        "low_conf_pct": 4.2,
    }
    assert by_id["beta"] == {
        "id": "beta",
        "title": "beta",
        "date": "2026-06-01",
        "lang": "en",
        "duration": 330,
        "folder": "beta.transcript",
        "low_conf_pct": 0.0,
    }
    assert by_id["gamma-quoted"] == {
        "id": "gamma-quoted",
        "title": "gamma",
        "date": "2026-06-03",
        "lang": "fr",
        "duration": 45,
        "folder": "gamma.transcript",
        "low_conf_pct": 1.5,
    }
    assert by_id["delta"] == {
        "id": "delta",
        "title": "delta",
        "date": "",
        "lang": "auto",
        "duration": 0,
        "folder": "delta.transcript",
        "low_conf_pct": 0.0,
    }
    assert by_id["nested-9"]["folder"] == "2026/nested.transcript"
    assert by_id["nested-9"]["title"] == "nested"
    assert by_id["nested-9"]["duration"] == 600


def test_rebuild_keeps_missing_folders_unless_prune(tmp_path):
    scriba = tmp_path / ".scriba"
    ui.upsert(scriba, _entry("gone-1", "2026-06-01"))
    ui.upsert(scriba, _entry("keep-1", "2026-06-02"))
    _write_transcript(
        tmp_path,
        "keep.transcript",
        "keep",
        "---\n"
        "id: keep-1\n"
        "date: 2026-06-02\n"
        "duration: 00:02:00\n"
        "language: en\n"
        "---\n",
    )

    res_keep = ui.rebuild(tmp_path, prune=False)
    assert len(res_keep["pruned"]) == 0
    assert len(res_keep["updated"]) == 1
    ids_keep = [r["id"] for r in json.loads((scriba / "index.json").read_text())["recordings"]]
    assert ids_keep == ["gone-1", "keep-1"]

    res_prune = ui.rebuild(tmp_path, prune=True)
    assert [r["id"] for r in res_prune["pruned"]] == ["gone-1"]
    recs = json.loads((scriba / "index.json").read_text())["recordings"]
    assert [r["id"] for r in recs] == ["keep-1"]
    assert recs[0]["duration"] == 120


def test_rebuild_dry_run_writes_nothing(tmp_path):
    _write_transcript(
        tmp_path,
        "fresh.transcript",
        "fresh",
        "---\nid: fresh-1\ndate: 2026-06-05\nduration: 00:01:00\nlanguage: en\n---\n",
    )
    # Without an existing .scriba directory, --dry-run creates nothing.
    res = _run_cli("rebuild", str(tmp_path), "--dry-run")
    assert res.returncode == 0, res.stderr
    assert "fresh-1" in res.stdout and "Dry run:" in res.stdout
    assert not (tmp_path / ".scriba").exists()

    # With an existing index containing a gone entry and a stale entry, --dry-run leaves it intact.
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    existing = {
        "schema_version": 1,
        "recordings": [
            _entry("gone-1", "2026-06-01"),
            _entry("keep-1", "2026-06-02"),
        ],
    }
    original = json.dumps(existing, indent=2).encode("utf-8")
    (scriba / "index.json").write_bytes(original)
    _write_transcript(
        tmp_path,
        "keep.transcript",
        "keep",
        "---\nid: keep-1\ndate: 2026-06-02\nduration: 00:03:00\nlanguage: ru\n---\n",
    )

    res2 = _run_cli("rebuild", str(tmp_path), "--prune", "--dry-run")
    assert res2.returncode == 0, res2.stderr
    assert "add    fresh-1" in res2.stdout
    assert "update keep-1" in res2.stdout
    assert "prune  gone-1" in res2.stdout
    _assert_untouched(scriba, original)
    assert not (scriba / "index.lock").exists()


@pytest.mark.parametrize("content", [
    b'{"schema_version": 1, "recordings": [{"id": "a"',
    b"",
    b"[]",
    b'{"recordings": ["bad"]}',
])
@pytest.mark.parametrize("dry_run", [False, True])
def test_rebuild_refuses_unreadable_index(tmp_path, content, dry_run):
    _write_transcript(
        tmp_path,
        "a.transcript",
        "a",
        "---\nid: a-1\ndate: 2026-06-05\nduration: 00:01:00\nlanguage: en\n---\n",
    )
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    (scriba / "index.json").write_bytes(content)

    with pytest.raises(ui.IndexReadError):
        ui.rebuild(tmp_path, dry_run=dry_run)
    _assert_untouched(scriba, content)

    cli_args = ["rebuild", str(tmp_path)] + (["--dry-run"] if dry_run else [])
    res = _run_cli(*cli_args)
    assert res.returncode == 1
    assert str(scriba / "index.json") in res.stderr
    assert "Traceback" not in res.stderr
    _assert_untouched(scriba, content)


def test_rebuild_writes_through_symlink_and_preserves_mode(tmp_path):
    synced = tmp_path / "synced"
    synced.mkdir()
    real = synced / "index.json"
    real.write_text(json.dumps({"schema_version": 1, "recordings": []}), encoding="utf-8")
    os.chmod(real, 0o644)

    rec_root = tmp_path / "recs"
    (rec_root / ".scriba").mkdir(parents=True)
    (rec_root / ".scriba" / "index.json").symlink_to(real)
    _write_transcript(
        rec_root,
        "call.transcript",
        "call",
        "---\nid: call-1\ndate: 2026-06-05\nduration: 00:01:30\nlanguage: en\n---\n",
    )

    ui.rebuild(rec_root)
    assert (rec_root / ".scriba" / "index.json").is_symlink()
    assert stat.S_IMODE(real.stat().st_mode) == 0o644
    assert [r["id"] for r in json.loads(real.read_text())["recordings"]] == ["call-1"]


def test_rebuild_refuses_dangling_symlink(tmp_path):
    scriba = tmp_path / ".scriba"
    scriba.mkdir()
    link = scriba / "index.json"
    link.symlink_to(tmp_path / "unmounted" / "index.json")
    with pytest.raises(ui.IndexReadError, match="does not exist"):
        ui.rebuild(tmp_path)
    assert link.is_symlink() and not link.exists()


def test_rebuild_missing_recordings_dir_fails_cleanly(tmp_path):
    res = _run_cli("rebuild", str(tmp_path / "does-not-exist"))
    assert res.returncode == 1
    assert "scriba:" in res.stderr
    assert "Traceback" not in res.stderr
