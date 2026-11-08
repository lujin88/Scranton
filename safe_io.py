"""Scranton: write state files so a crash or power cut never leaves half a file.

atomic_write writes to a temp file next to the target, fsyncs it and swaps it in.
quarantine moves a file that no longer parses aside (name.corrupt-<time>) instead of
letting the next save overwrite it, so nothing is lost silently.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path


def atomic_write(path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique per call: two threads saving the same file must not share a temp file.
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:6]}.tmp")
    with open(tmp, "w", encoding=encoding) as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def quarantine(path) -> Path | None:
    """Move an unreadable state file aside. Returns where it went."""
    path = Path(path)
    if not path.exists():
        return None
    dest = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        os.replace(path, dest)
        return dest
    except OSError:
        return None
