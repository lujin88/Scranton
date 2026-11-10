"""When ChatGPT's plan runs low, visual/motion work goes to the Gemini interns (Lu, 11-10).

The numbers come from Agent Monitor's own usage file (~/agent-monitor/usage.json), which it
refreshes every 5 minutes from Codex. Scranton only reads that file: it never uses Agent
Monitor's access key (that key can approve commands).

    [team.quota_handoff]
    enabled = true
    threshold = 90          # % of a ChatGPT window (5 hours or weekly) at which work moves
    back_below = 80         # moves back once every window is under this
    map = { visual = "visintern", motion = "motionintern" }

Anything unclear (no file, old numbers, a window that has already reset) means "not low":
work then goes where it was addressed, as before.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

DEFAULTS = {
    "enabled": True,
    "source": "codex",
    "threshold": 90,
    "back_below": 80,
    "map": {"visual": "visintern", "motion": "motionintern"},
    "usage_file": "~/agent-monitor/usage.json",
    "max_age_minutes": 30,   # Agent Monitor polls every 5 min; older numbers aren't trusted
}

_state = {"low": False, "percent": None, "label": ""}


def settings(cfg: dict | None) -> dict:
    raw = ((cfg or {}).get("team", {}) or {}).get("quota_handoff", {}) or {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in raw.items() if k in DEFAULTS})
    out["map"] = {str(k).lower(): str(v).lower() for k, v in (out.get("map") or {}).items()}
    return out


def read_usage(s: dict, now: float | None = None) -> tuple[float, str] | None:
    """Highest % used among the source's windows that are fresh and not yet reset."""
    now = time.time() if now is None else now
    try:
        data = json.loads(Path(s["usage_file"]).expanduser().read_text("utf-8"))
        entry = data.get(s["source"]) or {}
        updated = float(entry.get("updatedAt") or 0) / 1000.0
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if not updated or now - updated > float(s["max_age_minutes"]) * 60:
        return None
    best = None
    for w in entry.get("windows") or []:
        try:
            pct = float(w.get("usedPercent"))
        except (TypeError, ValueError):
            continue
        resets = w.get("resetsAt")
        if isinstance(resets, (int, float)) and 0 < resets <= now:
            continue   # that window has already started over
        if best is None or pct > best[0]:
            best = (pct, str(w.get("label") or ""))
    return best


def check(cfg: dict | None, now: float | None = None) -> tuple[bool, bool]:
    """Update the low/normal state. Returns (low, changed)."""
    s = settings(cfg)
    if not s["enabled"]:
        changed = _state["low"]
        _state.update(low=False, percent=None, label="")
        return False, changed
    got = read_usage(s, now)
    was = _state["low"]
    if got is None:
        low = False
    else:
        pct, label = got
        _state.update(percent=pct, label=label)
        low = pct >= float(s["threshold"]) if not was else pct >= float(s["back_below"])
    _state["low"] = low
    return low, low != was


def is_low() -> bool:
    return bool(_state["low"])


def status() -> dict:
    return dict(_state)


def _base(name: str) -> str:
    return re.sub(r"-\d+$", "", str(name or "").strip().lower())


def reroute(cfg: dict | None, targets: list[str], channel: str, sender: str) -> tuple[list[str], dict]:
    """Swap visual/motion for their interns while the plan is low. DMs stay as they are
    (a DM with @visual is that conversation). Returns (targets, {original: intern})."""
    if not _state["low"] or channel.startswith("dm-"):
        return targets, {}
    mapping = settings(cfg)["map"]
    agents = (cfg or {}).get("agents", {}) or {}
    out, moved = [], {}
    for t in targets:
        to = mapping.get(_base(t))
        if to and to in agents and _base(sender) != to:
            moved[t] = to
            t = to
        out.append(t)
    return list(dict.fromkeys(out)), moved


def notice(cfg: dict | None, low: bool) -> str:
    """The one message Scranton posts to the project manager when the state changes."""
    s = settings(cfg)
    pairs = "，".join(f"@{a} → @{b}" for a, b in s["map"].items())
    pct = _state.get("percent")
    where = f"{_state.get('label') or ''} {pct:.0f}%".strip() if pct is not None else ""
    if low:
        return (f"@pm ChatGPT 额度已用 {where}：从现在起发给视觉/动效的活自动转给 Gemini 实习生"
                f"（{pairs}，私信除外）。正在做的活请你看要不要转。降到 {s['back_below']:.0f}% 以下自动恢复。")
    return f"@pm ChatGPT 额度恢复（{where or '已重置'}）：视觉/动效的活回到 @visual、@motion。"
