"""Scranton: write state files so a crash or power cut never leaves half a file.

atomic_write writes to a temp file next to the target, fsyncs it and swaps it in.
quarantine moves a file that no longer parses aside (name.corrupt-<time>) instead of
letting the next save overwrite it, so nothing is lost silently.
"""
from __future__ import annotations

import os
import time
from pathlib import Path


def atomic_write(path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding=encoding) as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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
