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


# ---------------------------------------------------------------- is it really out? (Lu, 11-11)
# A teammate's screen saying "limit" is not proof: 11-10 every one of ~50 "I stopped: usage limit"
# from the ChatGPT teammates came at 90–93% of the week, and Cursor's "Other models" being full
# stopped webdev while Cursor's own models had 25% left. So before a teammate is stopped, look at
# the real numbers Agent Monitor keeps (~/agent-monitor/usage.json).
CURSOR_OWN = ("auto", "composer", "cursor-")


def is_cursor_own(model: str) -> bool:
    return str(model or "").lower().startswith(CURSOR_OWN)


def provider_usage(provider: str, model: str = "", usage_file: str = DEFAULTS["usage_file"],
                   now: float | None = None) -> dict | None:
    """{'pct': highest % used, 'label': window, 'resets': epoch|None} for the window this
    teammate draws on, or None when there are no fresh numbers (then the screen text decides)."""
    now = time.time() if now is None else now
    key = {"cursor": "cursor", "codex": "codex", "claude": "claude"}.get(provider)
    if not key:
        return None
    try:
        entry = (json.loads(Path(usage_file).expanduser().read_text("utf-8")) or {}).get(key) or {}
        updated = float(entry.get("updatedAt") or 0) / 1000.0
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if not updated or now - updated > float(DEFAULTS["max_age_minutes"]) * 60:
        return None
    wins = []
    for w in entry.get("windows") or []:
        label = str(w.get("label") or "")
        if key == "cursor":   # Cursor has two pools: its own models, and everyone else's
            own = label.lower().startswith("cursor")
            if own != is_cursor_own(model):
                continue
        try:
            pct = float(w.get("usedPercent"))
        except (TypeError, ValueError):
            continue
        resets = w.get("resetsAt")
        if isinstance(resets, (int, float)) and 0 < resets <= now:
            continue
        wins.append({"pct": pct, "label": label, "resets": resets if isinstance(resets, (int, float)) else None})
    return max(wins, key=lambda w: w["pct"]) if wins else None


def model_fallback(provider: str, model: str, usage_file: str = DEFAULTS["usage_file"]) -> str | None:
    """A model on the same plan that still has room, when only this model's quota is out."""
    m = str(model or "").lower()
    if provider == "cursor" and not is_cursor_own(m):
        own = provider_usage("cursor", "composer-2.5", usage_file)
        return "composer-2.5" if own is None or own["pct"] < 99 else None
    if provider == "gemini" and m and "flash" not in m:
        return "gemini-3.8-flash"   # Argon / Pro have their own quota; Flash is a separate pool
    return None


_RESETS_IN = re.compile(r"resets?\s+in\s+(?:(\d+)\s*d\s*)?(?:(\d+)\s*h\s*)?(?:(\d+)\s*m)?", re.I)
_RESETS_ON = re.compile(r"(?:ends|resets?)\s+on\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.I)


def reset_from_text(text: str, now: float | None = None) -> float | None:
    """'Resets in 155h21m9s' / 'cycle ends on 11/29/2026' → epoch seconds."""
    now = time.time() if now is None else now
    m = _RESETS_IN.search(text or "")
    if m and any(m.groups()):
        d, h, mi = (int(x or 0) for x in m.groups())
        return now + d * 86400 + h * 3600 + mi * 60
    m = _RESETS_ON.search(text or "")
    if m:
        mo, da, yr = (int(x) for x in m.groups())
        try:
            return time.mktime((yr, mo, da, 0, 0, 0, 0, 0, -1))
        except (OverflowError, ValueError):
            return None
    return None
