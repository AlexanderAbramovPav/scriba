# Transcript JSON sidecar schema

Every successful run persists a machine-readable sidecar inside the recording's
folder: `<title>.transcript/data/transcript.json`. While `<title>.transcript/<title>.md`
is the **human**-facing
artifact (clean, with only a frontmatter `low_confidence_pct` and a subtle `⚠︎`
on shaky turns), this JSON is the **AI**-facing input: it is honest about its
own uncertainty so downstream consumers can weight spans accordingly.

## Top level

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Currently `1`. Bump on any breaking shape change. |
| `language` | string | Detected (or forced) language code, e.g. `"ru"`, `"en"`. |
| `audio_duration_sec` | float | Source audio length in seconds (3 decimals). |
| `low_confidence_pct` | float | `0–100`. Share of words flagged as low-confidence (overlap, low ASR score, or shaky attribution). A whole-transcript honesty signal. |
| `segments` | array | See below. |

## `segments[]`

| Field | Type | Notes |
|---|---|---|
| `start` | float | Segment start (sec). |
| `end` | float | Segment end (sec). |
| `speaker` | string | Raw diarization label, e.g. `"SPEAKER_00"`. |
| `text` | string | Segment text. |
| `flags` | object | `{overlap, shaky_attribution}` — see below. |
| `words` | array | Per-word detail; see below. |

### `segments[].flags`

| Field | Type | Notes |
|---|---|---|
| `overlap` | bool | True if any word in the segment intersects simultaneous speech. |
| `shaky_attribution` | bool | True if any word's `speaker_conf` is below the attribution threshold. |

### `segments[].words[]`

| Field | Type | Notes |
|---|---|---|
| `word` | string | The token. |
| `start` | float | Word start (sec). May be absent when alignment failed for that word. |
| `end` | float | Word end (sec). |
| `asr_conf` | float ∈ [0,1] | whisperX/faster-whisper **alignment score** for the word (passed through). Lower = the acoustic match is weaker. |
| `overlap` | bool | True if the word's `[start, end)` intersects a region where **≥2 speakers** are simultaneously active. |
| `speaker_conf` | float ∈ [0,1] | **Attribution margin**: fraction of the word covered by its assigned speaker minus the best competing speaker. `1.0` = word sits fully inside its speaker's turn; `0.0` = fully contested. |

Words whose `start`/`end` are missing are skipped during enrichment and carry no
confidence fields.

## Guidance for downstream AI consumers

A high-quality transcript is one that is **honest about its own uncertainty**.
When summarizing, quoting, or attributing statements from this sidecar:

- **Down-weight `overlap = true` spans** — multiple people were talking at once,
  so both the words and the speaker label are less reliable there.
- **Down-weight low-confidence spans** — treat words with low `asr_conf` (weak
  acoustic match) and low `speaker_conf` (contested attribution) with caution;
  avoid quoting them verbatim or pinning a quote to a specific speaker.
- Use `low_confidence_pct` as a quick gauge of the whole transcript's reliability
  before relying on it heavily.
