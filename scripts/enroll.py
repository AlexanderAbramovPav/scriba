#!/usr/bin/env python3
"""Known-speaker enrollment matching (C3).

community-1 emits per-cluster speaker embeddings as a positional ndarray
(num_speakers, dim) ordered to match `speaker_diarization.labels()`. We coerce that
into {label: vector} (embeddings_to_dict), then, given reference embeddings for known
people, assign each cluster the best-matching name above a cosine threshold. Greedy by
descending similarity so a reference claims at most one cluster. Pure math; the
embedding extraction lives in the wrapper (reuses community-1).
"""
from __future__ import annotations
import math


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def embeddings_to_dict(labels, arr):
    """Map pyannote's positional speaker_embeddings ndarray (num_speakers, dim),
    ordered to match `labels`, into {label: list[float]}. None/empty -> {}."""
    if arr is None:
        return {}
    out = {}
    for i, lbl in enumerate(labels):
        if i < len(arr):
            out[lbl] = [float(x) for x in arr[i]]
    return out


def match_clusters(cluster_embs, ref_embs, threshold: float = 0.7):
    """Return {cluster_label: name}. Greedy: consider all (cluster,name) pairs by
    descending cosine; assign when both are still free and sim >= threshold."""
    pairs = []
    for cl, ce in cluster_embs.items():
        for name, re in ref_embs.items():
            pairs.append((cosine(ce, re), cl, name))
    pairs.sort(key=lambda p: p[0], reverse=True)
    used_cl, used_name, mapping = set(), set(), {}
    for sim, cl, name in pairs:
        if sim < threshold or cl in used_cl or name in used_name:
            continue
        mapping[cl] = name
        used_cl.add(cl)
        used_name.add(name)
    return mapping
