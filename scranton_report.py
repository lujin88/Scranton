"""Scranton weekly report: what got done, how long agents worked, what waited on Lu.

Only real, measured things. "Time you'd have spent" appears only when Lu sets her own
estimate (minutes per merged PR); Scranton never invents a baseline.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from safe_io import atomic_write

ROOT = Path(__file__).parent
STATS = ROOT / "data" / "stats.json"
SETTINGS = ROOT / "data" / "report.json"
PR_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
MERGED_RE = re.compile(r"\bmerged\b|已合并|合并了|合并完成|merge-pr\.sh", re.I)

_lock = threading.Lock()
_stats: dict = {}
_last_seen: dict[str, float] = {}
_dirty_at = 0.0


def _load():
    global _stats
    try:
        _stats = json.loads(STATS.read_text("utf-8"))
    except (OSError, ValueError):
        _stats = {}


_load()


def note_active(agent: str, active: bool, now: float | None = None) -> None:
    """Called on every heartbeat: adds the seconds an agent spent working (capped per beat)."""
    global _dirty_at
    now = now or time.time()
    base = agent.split("-")[0]
    with _lock:
        prev = _last_seen.get(base)
        _last_seen[base] = now
        if not active or prev is None:
            return
        delta = min(max(now - prev, 0.0), 10.0)
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        d = _stats.setdefault(day, {})
        d[base] = round(d.get(base, 0.0) + delta, 1)
        if now - _dirty_at > 60:
            _dirty_at = now
            atomic_write(STATS, json.dumps(_stats))


def settings() -> dict:
    try:
        s = json.loads(SETTINGS.read_text("utf-8"))
    except (OSError, ValueError):
        s = {}
    m = s.get("minutes_per_pr")
    return {"minutes_per_pr": m if isinstance(m, (int, float)) and 0 < m <= 60 * 40 else None}


def set_minutes_per_pr(value) -> dict:
    if value in (None, "", 0):
        atomic_write(SETTINGS, json.dumps({}))
        return settings()
    v = float(value)
    if not 0 < v <= 60 * 40:
        raise ValueError("between 1 minute and 40 hours")
    atomic_write(SETTINGS, json.dumps({"minutes_per_pr": v}))
    return settings()


def build(messages: list[dict], team: dict, owner: str, days: int = 7, now: float | None = None) -> dict:
    now = now or time.time()
    since = now - days * 86400
    owner_l = owner.lower()
    agents = {h for h in team}
    recent = [m for m in messages if float(m.get("timestamp") or 0) >= since and (m.get("type") or "chat") == "chat"]
    base = lambda s: str(s or "").split("-")[0].lower()

    # 1. what got done: PRs agents posted, merged if any message says so with that link
    prs: dict[str, dict] = {}
    for m in recent:
        who = base(m.get("sender"))
        for url in PR_RE.findall(str(m.get("text") or "")):
            p = prs.setdefault(url, {"url": url, "by": who if who in agents else "", "merged": False,
                                     "first": m.get("timestamp"), "title": ""})
            if not p["by"] and who in agents:
                p["by"] = who
            if not p["title"] and who in agents:
                t = PR_RE.sub("", str(m.get("text") or "")).strip(" |:-—\n")
                p["title"] = t.splitlines()[0][:120] if t else ""
            if MERGED_RE.search(str(m.get("text") or "")):
                p["merged"] = True
    shipped = sorted(prs.values(), key=lambda p: (not p["merged"], -(p["first"] or 0)))

    # 2. measured work per agent
    with _lock:
        stats = dict(_stats)
    work = []
    for h in sorted(agents):
        secs = sum(float((stats.get(time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))) or {}).get(h, 0))
                   for i in range(days))
        replies = sum(1 for m in recent if base(m.get("sender")) == h)
        if secs or replies:
            work.append({"agent": h, "hours": round(secs / 3600, 1), "replies": replies})
    work.sort(key=lambda w: (-w["hours"], -w["replies"]))

    # 3. waiting on you: agent messages that @ you, and how long until you wrote in that channel
    waits, open_items = [], []
    tag = re.compile(r"@" + re.escape(owner) + r"(?![\w-])", re.I)
    for m in recent:
        if base(m.get("sender")) not in agents or not tag.search(str(m.get("text") or "")):
            continue
        t0 = float(m.get("timestamp") or 0)
        ch = m.get("channel", "general")
        reply = next((float(x.get("timestamp") or 0) for x in recent
                      if x.get("channel", "general") == ch and str(x.get("sender", "")).lower() == owner_l
                      and float(x.get("timestamp") or 0) > t0), None)
        if reply is None:
            open_items.append({"id": m.get("id"), "channel": ch, "by": base(m.get("sender")),
                               "text": str(m.get("text") or "")[:140], "since": t0})
        else:
            waits.append(reply - t0)
    avg_wait_min = round(sum(waits) / len(waits) / 60) if waits else None

    merged = sum(1 for p in shipped if p["merged"])
    st = settings()
    estimate = None
    if st["minutes_per_pr"] and merged:
        estimate = {"minutes_per_pr": st["minutes_per_pr"], "hours": round(merged * st["minutes_per_pr"] / 60, 1)}
    return {
        "days": days,
        "shipped": shipped[:50],
        "counts": {"prs": len(shipped), "merged": merged,
                   "agent_hours": round(sum(w["hours"] for w in work), 1),
                   "replies": sum(w["replies"] for w in work)},
        "work": work,
        "waiting": {"avg_minutes": avg_wait_min, "answered": len(waits), "open": open_items[:20]},
        "estimate": estimate,
        "settings": st,
    }
