import subprocess, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "rename_speakers.py"

MD = """---
speakers_detected: 2
---

## Спикеры — опознай, кто есть кто

**Speaker 1** (говорит 60% времени). Характерные реплики:
> [00:00:01] «Привет.»

**Speaker 2** (говорит 40% времени). Характерные реплики:
> [00:00:04] «Да.»

## Транскрипт

**Speaker 1** [00:00:01]
Привет всем.

**Speaker 2** [00:00:04]
Да, поехали.
"""


def write(tmp_path):
    p = tmp_path / "t.md"; p.write_text(MD, encoding="utf-8"); return p


def test_positional_mapping(tmp_path):
    p = write(tmp_path)
    subprocess.run([sys.executable, str(SCRIPT), str(p), "Иван,Аня"], check=True)
    out = p.read_text(encoding="utf-8")
    assert "**Иван** [00:00:01]" in out
    assert "**Аня** [00:00:04]" in out
    assert "Speaker 1" not in out and "Speaker 2" not in out


def test_explicit_map_and_out(tmp_path):
    p = write(tmp_path); o = tmp_path / "named.md"
    subprocess.run([sys.executable, str(SCRIPT), str(p),
                    "--map", "Speaker 2=Аня,Speaker 1=Иван", "--out", str(o)], check=True)
    out = o.read_text(encoding="utf-8")
    assert "**Иван**" in out and "**Аня**" in out
    assert p.read_text(encoding="utf-8") == MD  # original untouched when --out given


def test_zero_renamed_fails_and_leaves_file_unchanged(tmp_path):
    # PR #9's `--map "Hablante 1=…"` used to print "Renamed 2 speaker(s)" and exit 0.
    p = write(tmp_path); o = tmp_path / "named.md"
    r = subprocess.run([sys.executable, str(SCRIPT), str(p),
                        "--map", "Hablante 1=Alice,Hablante 2=Bob", "--out", str(o)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "Hablante 1" in r.stderr and "Speaker N" in r.stderr
    assert "renamed 0" in r.stderr
    assert p.read_text(encoding="utf-8") == MD
    assert not o.exists()


def test_partial_match_renames_and_names_the_missing_label(tmp_path):
    p = write(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPT), str(p), "Иван,Аня,Олег"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "Speaker 3" in r.stderr  # warned: no such label
    assert "Renamed 2 speaker(s), 4 label(s)" in r.stderr
    out = p.read_text(encoding="utf-8")
    assert "**Иван**" in out and "**Аня**" in out and "Олег" not in out
