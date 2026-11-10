"""How big a teammate's current session is, read from the CLI's own log (Lu, 11-10).

Fresh sessions used to start over only after N hours or N messages. The data (11-08 to 11-10)
showed the cost is the size of the context, re-sent on every call: ChatGPT teammates averaged
~140k tokens per call, up to 244k. So a session is also handed over once its context passes a
size. This module only reads logs; it never changes them.

  Claude Code: ~/.claude/projects/<cwd, every non-alphanumeric as ->/<session>.jsonl, assistant `usage`
  Codex:       ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, `token_count` events

Other apps (Cursor, Gemini) return None: no size, so only hours/messages apply.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

TAIL = 256 * 1024   # the last call is near the end; never read a whole multi-MB log


def _tail_lines(path: Path) -> list[str]:
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - TAIL))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "ignore").splitlines()
    return lines[1:] if size > TAIL else lines   # the first line may be cut


def _claude_dir(cwd: str, home: Path) -> Path:
    return home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))   # Claude Code names the folder this way


def claude_context(cwd: str, since: float, home: Path | None = None) -> int | None:
    folder = _claude_dir(cwd, home or Path.home())
    try:
        files = [p for p in folder.glob("*.jsonl") if p.stat().st_mtime >= since]
    except OSError:
        return None
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    for line in reversed(_tail_lines(newest)):
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message") or {}
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        u = msg.get("usage") or {}
        n = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) \
            + int(u.get("cache_creation_input_tokens") or 0)
        if n:
            return n
    return None


def _codex_meta(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            first = f.readline()
        d = json.loads(first)
    except (OSError, ValueError):
        return {}
    return d.get("payload") or {} if d.get("type") == "session_meta" else {}


def codex_context(cwd: str, since: float, home: Path | None = None) -> int | None:
    base = Path(os.environ.get("CODEX_HOME") or (home or Path.home()) / ".codex") / "sessions"
    days = {time.strftime("%Y/%m/%d", time.localtime(t)) for t in (since, time.time(), time.time() - 86400)}
    cands = []
    for day in days:
        try:
            cands += [p for p in (base / day).glob("rollout-*.jsonl") if p.stat().st_mtime >= since]
        except OSError:
            pass
    want = str(Path(cwd).resolve()) if cwd else ""
    for p in sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True):
        meta = _codex_meta(p)
        if isinstance(meta.get("source"), dict):   # a subagent's own log, not the teammate's session
            continue
        if want and str(Path(meta.get("cwd") or "").resolve()) != want:
            continue
        for line in reversed(_tail_lines(p)):
            if '"token_count"' not in line:
                continue
            try:
                info = (json.loads(line).get("payload") or {}).get("info") or {}
            except ValueError:
                continue
            n = int((info.get("last_token_usage") or {}).get("input_tokens") or 0)
            if n:
                return n
        return None
    return None


def current_context(command: str, cwd: str, since: float, home: Path | None = None) -> int | None:
    app = os.path.basename(str(command or "")).lower()
    try:
        if app.startswith("claude"):
            return claude_context(cwd, since, home)
        if app.startswith("codex"):
            return codex_context(cwd, since, home)
    except Exception:
        return None
    return None
