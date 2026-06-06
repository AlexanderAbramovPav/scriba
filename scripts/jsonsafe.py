#!/usr/bin/env python3
"""JSON serialization safety net for the sidecar.

whisperX/pyannote return NumPy scalars (np.float32/np.float64/np.bool_) inside
segment/word dicts. The stdlib json encoder can't serialize those and aborts the
whole transcript write. `json_default` converts any NumPy-like scalar/array to a
native Python type — passed as `json.dumps(..., default=json_default)`. Duck-typed
so it needs no numpy import (and is testable without numpy).
"""
from __future__ import annotations


def json_default(o):
    # NumPy 0-d scalar (np.float64, np.bool_, np.int64, …): has .item(), no len().
    item = getattr(o, "item", None)
    if callable(item):
        try:
            if not hasattr(o, "__len__") or getattr(o, "ndim", None) == 0:
                return o.item()
        except (TypeError, ValueError):
            pass
    # NumPy array (or anything array-like with .tolist()).
    tolist = getattr(o, "tolist", None)
    if callable(tolist):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
