import json, subprocess, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "json_to_md.py"

SYNTH = {
    "language": "ru",
    "segments": [
        {"start": 1.0, "end": 4.5, "text": "Привет всем, начнём встречу.", "speaker": "SPEAKER_00"},
        {"start": 4.6, "end": 6.0, "text": "Да, поехали.", "speaker": "SPEAKER_01"},
        {"start": 6.1, "end": 9.0, "text": "Сегодня обсудим план на квартал.", "speaker": "SPEAKER_00"},
    ],
}


def run(tmp_path, data, **extra):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    args = [sys.executable, str(SCRIPT), str(p), "--source", "meeting.webm",
            "--title", "meeting"]
    for k, v in extra.items():
        args += [f"--{k}", str(v)]
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def test_frontmatter_and_speaker_mapping(tmp_path):
    out = run(tmp_path, SYNTH)
    assert out.startswith("---")
    assert "language: ru" in out
    assert "speakers_detected: 2" in out
    assert "# meeting" in out  # H1 title
    assert "data: data/transcript.json" in out
    assert "clips: data/" in out
    assert "**Speaker 1**" in out and "**Speaker 2**" in out
    assert "SPEAKER_00" not in out  # raw labels must be remapped


def test_turn_merging_and_timecodes(tmp_path):
    out = run(tmp_path, SYNTH)
    assert "**Speaker 1** [00:00:01]" in out
    assert "**Speaker 2** [00:00:04]" in out
    assert "## Transcript" in out
    assert "## Speakers" in out


def test_real_fixture_if_present(tmp_path):
    fx = HERE / "fixtures" / "sample.json"
    if not fx.exists():
        return
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(fx), "--source", "clip.wav"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "## Transcript" in out and "**Speaker 1**" in out
