# File layout (C6)

Every recording becomes a **portable folder** you can move, zip, or sync anywhere
without breaking the embedded audio. The Markdown and its assets travel together.

## Per-recording folder

```
<recordings-dir>/
├── <title>.transcript/          # one folder per recording — self-contained, portable
│   ├── <title>.md               # the human-facing transcript (H1 title + frontmatter)
│   └── data/                    # everything the MD points at, via RELATIVE paths
│       ├── transcript.json      # rich machine-readable sidecar (per-word confidence, overlap, speakers)
│       └── speaker-1.wav …      # one ≤10 s voice clip per speaker, for ID-by-ear
└── .scriba/                     # hidden corpus state, shared across all recordings here
    ├── index.json               # AI navigation index — one entry per recording
    ├── glossary.txt             # project-scoped term biasing (C5a)
    └── voiceprints/             # persistent speaker embeddings (C3 enrollment)
```

`<title>.md` references its assets with paths relative to itself
(`data/transcript.json`, `<audio src="data/speaker-1.wav">`), so the whole
`<title>.transcript/` folder is movable as a unit — Obsidian, VS Code, and GitHub
all resolve the relative `<audio>` players correctly.

The MD frontmatter carries pointers so an AI (or a human) never has to guess:

```yaml
---
id: q3-planning-sync-1717603200   # stable index key (<stem>-<epoch>)
source: zoom_0.mp4                # original filename, preserved
date: 2026-06-05
duration: 00:42:10
model: large-v3 (whisperX+pyannote)
language: en
low_confidence_pct: 3.1          # present only when computed (C2)
speakers_detected: 3
data: data/transcript.json        # the JSON sidecar
clips: data/                      # where the voice clips live
---

# q3-planning-sync
```

## The corpus index — `.scriba/index.json`

So an AI can find a meeting by reading **one** small file instead of scanning the
whole folder tree:

```json
{
  "schema_version": 1,
  "recordings": [
    {
      "id": "q3-planning-sync-1717603200",
      "title": "q3-planning-sync",
      "date": "2026-06-05",
      "lang": "en",
      "duration": 2530,
      "folder": "q3-planning-sync.transcript",
      "low_conf_pct": 3.1
    }
  ]
}
```

- **Upsert by `id`** — re-transcribing the same recording replaces its entry rather
  than duplicating it. Writes are **atomic** (temp file + `os.replace`), so a crash
  mid-write can never corrupt the index.
- Entries are sorted by `date`.
- `folder` is the per-recording folder name, relative to the index's parent dir.

### Index discovery walks up

`update_index.find_index_dir(start)` walks **up** from any path until it finds a
directory containing `.scriba/`. That means an AI handed a single transcript file
deep in the tree can locate the corpus index by walking toward the root — the
index always lives at the recordings root, not next to each recording.

## Two distinct voice stores — don't conflate them

| Store | Path | What it is | Lifetime |
|---|---|---|---|
| **Listening clips** | `<title>.transcript/data/speaker-*.wav` | Short ≤10 s WAVs cut from this recording, for a human to *play* and recognise the voice. | Per-recording; ship with the folder. |
| **Voiceprints** | `.scriba/voiceprints/` | Persistent speaker **embeddings** for known people (C3 enrollment) — used to auto-name speakers across future recordings. | Corpus-wide; never embedded in a transcript. |

The clips are for *ears*; the voiceprints are for *matching*. They live in different
places on purpose: clips are disposable per-recording artifacts, voiceprints are
durable corpus knowledge.

## Auto-naming rule (C6d)

The output stem is derived in `scripts/naming.py`:

1. **Source filename → kebab.** `Q3 Planning Sync.mov` → `q3-planning-sync`.
2. **Generic source name → ask the agent.** If the source name is uninformative
   (`zoom_0`, `GMT20260605-120000`, `recording`, `video`, `audio`, a bare date,
   or anything shorter than 4 chars after kebab-casing), the agent supplies a
   meaningful `--title`; we kebab that instead.
3. **`--title` always wins.** When provided, it overrides the source name regardless.

The resolved stem is used for the folder (`<stem>.transcript/`), the MD file
(`<stem>.md`), the `id` (`<stem>-<epoch>`), and the H1 title. The original filename
is always preserved in the `source:` frontmatter field, so nothing is lost.
