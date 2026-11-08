"""Scranton: Grok Bot as "幕僚长 (Grok)", a chief of staff who can post and read in Scranton.

Grok Bot runs in xAI's cloud and can't reach this Mac's localhost. With "run commands on your
local computer" turned on in Grok Bot, it runs `./scranton.sh grok …` here instead. That
command talks to the local server with its own token (data/grok-token), which can only:
  - post as "grok" in an existing channel or an agent's DM
  - read messages (a channel, or what mentions @grok / the owner)
It can't post as Lu, approve anything, change settings, or start/stop agents.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from safe_io import atomic_write

HANDLE = "grok"
LABEL = "幕僚长 (Grok)"
MAX_TEXT = 8000
_data = Path(__file__).resolve().parent / "data"


def setup(data_dir):
    global _data
    _data = Path(data_dir)


def token_path() -> Path:
    return _data / "grok-token"


def token() -> str:
    """The token, made on first use (readable by this macOS user only)."""
    p = token_path()
    try:
        t = p.read_text("utf-8").strip()
        if len(t) >= 32:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(32)
    atomic_write(p, t)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return t


def check(header_value: str) -> bool:
    return bool(header_value) and secrets.compare_digest(header_value, token())


def line(m: dict, labels: dict) -> str:
    who = labels.get(str(m.get("sender", "")).split("-")[0], m.get("sender", ""))
    where = m.get("channel", "general")
    reply = f" ↳{m['reply_to']}" if m.get("reply_to") is not None else ""
    text = re.sub(r"\s+\n", "\n", str(m.get("text") or "")).strip()
    return f"[{m.get('id')}] #{where} {m.get('time', '')[:5]} {who}{reply}: {text}"
