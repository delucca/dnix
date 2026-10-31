"""Shared spill-to-disk output helpers for ~/.config/ai skill scripts.

Extracted from ~26 near-identical ``emit(label, payload)`` copies. Each script
binds its own spill directory (e.g. ``Path.home() / ".cache" / "slack-cm"``,
usually via :func:`secure_cache_dir`) via :func:`make_emit` and calls the
returned ``emit(label, payload)``. Short payloads print inline; large payloads
spill to a timestamped file under the spill dir and print a 1500-char preview
so the calling agent can Read the rest.

Standardised here (each was drifted across copies):

* inline threshold measured in **bytes** (``len(body.encode())``), not chars,
* ``None`` payloads render as ``"(empty response)"`` (was literal ``"None"``),
* the trailing-newline fix on the preview (some copies had dropped it).

Renders to ``~/.config/ai/common/lib/emit.py``; imported through a ``sys.path`` shim.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import time
from pathlib import Path

INLINE_LIMIT = 4000  # bytes; above this the payload spills to disk
PREVIEW_CHARS = 1500
LABEL_MAX = 80  # cap the sanitised label so the spill filename stays sane
CACHE_MAX_AGE_DAYS = 7  # prune spill files older than this on each call


def secure_cache_dir(name: str, *, max_age_days: int = CACHE_MAX_AGE_DAYS) -> Path:
    """Return ``~/.cache/<name>-cm``, created 0700 and verified owned by us.

    A fixed, predictable ``/tmp/<name>-cm`` let any local user read spilled
    output, or pre-create the path to intercept it. Moving under the user's
    own home closes most of that, but a shared ``~/.cache`` is still worth
    checking rather than trusting blindly — mirrors the ``_secure_out_dir()``
    pattern used by uid-namespaced ``/tmp`` spill dirs (here namespaced by
    living under ``$HOME`` instead), self-healing the mode if it drifted.
    Unlike ``/tmp``, macOS never reaps ``~/.cache``, so this also prunes spill
    files older than ``max_age_days`` from this directory only on every call.
    """
    base = Path.home() / ".cache" / f"{name}-cm"
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = base.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        sys.exit(f"Refusing to use {base}: not a directory you own.")
    if st.st_mode & 0o077:
        base.chmod(0o700)
    _prune_old(base, max_age_days)
    return base


def _prune_old(base: Path, max_age_days: int) -> None:
    """Best-effort delete of files older than ``max_age_days`` inside ``base``."""
    cutoff = time.time() - max_age_days * 86400
    for entry in base.iterdir():
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            pass  # lost a race with another process; not worth failing over


def _safe_label(label: str) -> str:
    """Reduce a caller-supplied label to a safe single path segment.

    Labels are frequently free text (a Grafana search query, a Jaeger tag key,
    a pipeline UUID). A ``/`` — or any other separator — would turn the spill
    path into a nonexistent subdirectory and raise ``FileNotFoundError`` on
    write, exactly in the large-result case the spill path exists for. Strip to
    a filename-safe set and cap the length. Well-formed labels are unchanged.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._-")
    return (safe or "out")[:LABEL_MAX]


def _render(payload, raw_text: bool) -> str:
    """Coerce a payload to the text body that gets printed or spilled."""
    if payload is None:
        return "(empty response)"
    if raw_text or isinstance(payload, str):
        return payload if isinstance(payload, str) else str(payload)
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return str(payload)


def emit_to(
    out_dir,
    label: str,
    payload,
    *,
    raw_text: bool = False,
    inline_limit: int = INLINE_LIMIT,
) -> None:
    """Print short payloads inline; spill large ones to ``out_dir`` with a preview."""
    body = _render(payload, raw_text)
    if len(body.encode()) <= inline_limit:
        print(body)
        return
    out_dir = Path(out_dir)
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}-{_safe_label(label)}.json"
    path.write_text(body, encoding="utf-8")
    head = body[:PREVIEW_CHARS]
    print(f"# {label}: {len(body)} bytes, saved to {path}")
    print("# first 1500 chars below; read the file for the rest\n")
    print(head)
    if not head.endswith("\n"):
        print()
    print(f"# ...truncated; full payload at {path}")


def make_emit(out_dir, *, inline_limit: int = INLINE_LIMIT):
    """Return an ``emit(label, payload, raw_text=False)`` bound to ``out_dir``."""

    def emit(label: str, payload, raw_text: bool = False) -> None:
        emit_to(out_dir, label, payload, raw_text=raw_text, inline_limit=inline_limit)

    return emit
