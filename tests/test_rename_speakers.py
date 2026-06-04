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
