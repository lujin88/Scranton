"""Scranton: notice when Lu is back after being away, so the project manager can send
everything that needs her in one list instead of agents waiting on her one by one."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from safe_io import atomic_write

ROOT = Path(__file__).resolve().parent
AWAY_HOURS = 2
_lock = threading.Lock()
_path = ROOT / "data" / "presence.json"


def setup(data_dir):
    global _path
    _path = Path(data_dir) / "presence.json"


def _load() -> dict:
    s = {"enabled": True, "last_seen": 0.0}
    try:
        s.update(json.loads(_path.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return s


def settings() -> dict:
    s = _load()
    return {"enabled": bool(s.get("enabled", True)), "away_hours": AWAY_HOURS}


def set_enabled(on: bool) -> dict:
    with _lock:
        s = _load()
        s["enabled"] = bool(on)
        atomic_write(_path, json.dumps(s))
    return settings()


def seen(now: float | None = None) -> float | None:
    """Record that Lu is looking at Scranton. Returns how long she was away (seconds) when
    this is the first sign of her after AWAY_HOURS or more and catch-up is on; else None."""
    now = now or time.time()
    with _lock:
        s = _load()
        last = float(s.get("last_seen") or 0)
        s["last_seen"] = now
        # Write at most once a minute: pings arrive often.
        if now - last >= 60 or not last:
            atomic_write(_path, json.dumps(s))
    if last and s.get("enabled", True) and now - last >= AWAY_HOURS * 3600:
        return now - last
    return None


def catch_up_text(owner: str, away: float) -> str:
    hours = int(away // 3600)
    gone = f"离开了 {hours} 小时" if hours < 48 else f"离开了 {hours // 24} 天"
    return (f"@pm {owner} 回来了（{gone}）。把待问清单一次发给 @{owner}：每个问题一行，"
            f"下面每个选项单独一行写成「A. …」「B. …」（团队建议放第一个并标推荐），她点按钮就能回答；再用一行说这段时间做完了什么（附 PR 链接）。"
            f"清单是空的就只说一句「没有要你定的事」。")
