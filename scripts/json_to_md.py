#!/usr/bin/env python3
"""Convert whisply/whisperX diarized JSON to a Markdown transcript.

Usage: json_to_md.py INPUT.json --source NAME [--model M] [--date YYYY-MM-DD]
                     [--audio PATH --media-dir DIR]
Writes Markdown to stdout.

When `--audio` and `--media-dir` are both given, ffmpeg cuts a small WAV clip
for each speaker sample (3 per speaker) and the resulting `<audio>` element is
embedded in the Markdown right under the textual quote — so a human reader
can both read and *hear* the sample when they don't recognise the voice
from the text alone.
"""
import argparse, json, pathlib, subprocess, sys
from collections import Counter
from datetime import date as _date


def _dominant_speaker(words):
    """Majority speaker label among a chunk's words, or None if unlabeled."""
    spk = [w.get("speaker") for w in (words or []) if w.get("speaker")]
    return Counter(spk).most_common(1)[0][0] if spk else None


def load_segments(data):
    """Return (segments, language). Handles the whisply nested shape
    ({"transcription": {"<lang>": {"chunks": [...]}}}, speaker carried on words)
    and the flat whisperX shape ({"segments": [...]} with per-segment speaker)."""
    if isinstance(data, dict) and isinstance(data.get("transcription"), dict):
        tr = data["transcription"]
        lang = next(iter(tr), "auto")
        chunks = (tr.get(lang) or {}).get("chunks") or []
        norm, last = [], "SPEAKER_00"
        for c in chunks:
            ts = c.get("timestamp") or [0.0, 0.0]
            start = float(ts[0]) if ts and ts[0] is not None else 0.0
            end = float(ts[1]) if len(ts) > 1 and ts[1] is not None else start
            spk = _dominant_speaker(c.get("words")) or last
            last = spk
            norm.append({"start": start, "end": end,
                         "text": (c.get("text") or "").strip(), "speaker": spk})
        return [s for s in norm if s["text"]], lang

    if isinstance(data, dict):
        segs = data.get("segments") or data.get("transcriptions") or data.get("result")
        lang = data.get("language") or data.get("lang") or "auto"
    else:
        segs, lang = data, "auto"
    if isinstance(segs, dict):
        segs = list(segs.values())
    norm = []
    for s in segs or []:
        fl = s.get("flags") or {}
        flag = bool(fl.get("overlap") or fl.get("shaky_attribution"))
        norm.append({
            "start": float(s.get("start", 0.0)),
            "end": float(s.get("end", s.get("start", 0.0))),
            "text": (s.get("text") or "").strip(),
            "speaker": s.get("speaker") or _dominant_speaker(s.get("words")) or "SPEAKER_00",
            "flag": flag,
        })
    return [s for s in norm if s["text"]], lang


def hhmmss(t):
    t = int(t)  # floor: timecodes mark the start of an utterance, never rounded up
    return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"


def map_speakers(segs):
    mapping, n, order = {}, 0, []
    for s in segs:
        raw = s["speaker"]
        if raw not in mapping:
            n += 1; mapping[raw] = f"Speaker {n}"; order.append(mapping[raw])
    for s in segs:
        s["spk"] = mapping[s["speaker"]]
    return order


def talk_time(segs):
    tot = {}
    for s in segs:
        tot[s["spk"]] = tot.get(s["spk"], 0.0) + (s["end"] - s["start"])
    grand = sum(tot.values()) or 1.0
    return {k: v / grand for k, v in tot.items()}


def samples(segs, spk, k=3):
    cand = sorted([s for s in segs if s["spk"] == spk],
                  key=lambda s: len(s["text"]), reverse=True)[:k]
    return sorted(cand, key=lambda s: s["start"])


def merge_turns(segs):
    turns = []
    for s in segs:
        if turns and turns[-1]["spk"] == s["spk"]:
            turns[-1]["text"] += " " + s["text"]
            turns[-1]["end"] = s["end"]
        else:
            turns.append(dict(s))
        # A turn is flagged if any constituent segment was flagged.
        turns[-1]["flag"] = turns[-1].get("flag") or s.get("flag")
    return turns


def cut_audio_clip(audio_path, out_path, start, end, pad=0.3, max_duration=10.0):
    """Extract [start-pad, min(end+pad, start+max_duration)] from audio_path into out_path.

    Re-encoding to pcm_s16le for accurate timestamps (`-c copy` snaps to keyframes).
    Caps clip length at `max_duration` seconds — 10 s is more than enough for voice ID;
    longer clips are wasted bytes.

    Returns True on success, False if ffmpeg failed or audio_path is missing.
    """
    if not audio_path or not pathlib.Path(audio_path).exists():
        return False
    s = max(0.0, float(start) - pad)
    e = float(end) + pad
    if max_duration and (e - s) > max_duration:
        e = s + max_duration
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
             "-i", audio_path, "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(out_path)],
            check=True, capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def voice_sample(segs, spk):
    """Pick one segment for voice identification — the longest one by audio duration.

    Longer = more continuous speech = clearer for voice ID. Returns segment dict or None.
    """
    spk_segs = [s for s in segs if s["spk"] == spk]
    if not spk_segs:
        return None
    return max(spk_segs, key=lambda s: s["end"] - s["start"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--source", required=True)
    ap.add_argument("--model", default="large-v3 (whisperX+pyannote)")
    ap.add_argument("--date", default=_date.today().isoformat())
    ap.add_argument("--audio", default=None,
                    help="path to source audio/video; when set together with --media-dir, "
                         "extracts a clip per speaker sample for embedded playback.")
    ap.add_argument("--media-dir", default=None,
                    help="directory to write audio clips into (relative paths in the MD will "
                         "be computed from the MD's location — pass an absolute path).")
    ap.add_argument("--title", default=None,
                    help="human-facing recording title; becomes the H1 and the page title. "
                         "Falls back to --source when absent.")
    ap.add_argument("--id", default=None,
                    help="stable recording id (used as the index key); emitted as frontmatter "
                         "`id:` when provided.")
    ap.add_argument("--clips-rel", default="data",
                    help="directory (relative to the MD) holding the voice clips and the JSON "
                         "sidecar — embedded `<audio src=…>` paths are computed from it.")
    a = ap.parse_args()

    data = json.loads(pathlib.Path(a.input).read_text(encoding="utf-8"))
    segs, lang = load_segments(data)
    if not segs:
        print("ERROR: no segments found in JSON", file=sys.stderr); sys.exit(2)
    order = map_speakers(segs)
    pct = talk_time(segs)
    duration = hhmmss(max(s["end"] for s in segs))

    title = a.title or a.source
    out = []
    out.append("---")
    if a.id:
        out.append(f"id: {a.id}")
    out.append(f"source: {a.source}")
    out.append(f"date: {a.date}")
    out.append(f"duration: {duration}")
    out.append(f"model: {a.model}")
    out.append(f"language: {lang}")
    low_pct = data.get("low_confidence_pct") if isinstance(data, dict) else None
    if low_pct is not None:
        out.append(f"low_confidence_pct: {low_pct}")
    out.append(f"speakers_detected: {len(order)}")
    # Pointers into the portable per-recording folder (C6): the JSON sidecar and the
    # voice clips both live under <clips-rel>/ next to this MD.
    out.append(f"data: {a.clips_rel}/transcript.json")
    out.append(f"clips: {a.clips_rel}/")
    out.append("---\n")

    out.append(f"# {title}\n")

    out.append("## Speakers — identify who's who\n")
    media_dir = pathlib.Path(a.media_dir).resolve() if a.media_dir else None
    do_clips = bool(a.audio and media_dir)
    # Wipe any old per-sample clips from prior runs (we now only emit one clip per speaker).
    if do_clips and media_dir.exists():
        for old in media_dir.glob("speaker-*.wav"):
            old.unlink()
    for spk_idx, spk in enumerate(order, start=1):
        out.append(f"**{spk}** ({round(pct.get(spk, 0) * 100)}% of speaking time).")
        if do_clips:
            vs = voice_sample(segs, spk)
            if vs and cut_audio_clip(a.audio, media_dir / f"speaker-{spk_idx}.wav",
                                      vs["start"], vs["end"], max_duration=10.0):
                rel = f"{a.clips_rel}/speaker-{spk_idx}.wav"
                out.append("")
                out.append(f'<audio controls preload="none" src="{rel}"></audio>')
        out.append("")
        out.append("Sample utterances:")
        for s in samples(segs, spk):
            out.append(f"> [{hhmmss(s['start'])}] \"{s['text']}\"")
        out.append("")

    out.append("## Transcript\n")
    for t in merge_turns(segs):
        mark = " ⚠︎" if t.get("flag") else ""
        out.append(f"**{t['spk']}** [{hhmmss(t['start'])}]{mark}")
        out.append(t["text"]); out.append("")

    sys.stdout.write("\n".join(out).rstrip() + "\n")


if __name__ == "__main__":
    main()
