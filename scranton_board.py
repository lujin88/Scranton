"""Lu's asks, one line each (Lu, 11-11: 20 messages in a morning asking "还没改吗 / 为什么还是旧的").

The project manager keeps one row per thing Lu asked for: what she asked, where it is now, who has
it, when it's due, a link. Rows change in place instead of new messages; Scranton pins the list at the
top of the channel. Stored in data/board.json as {channel: [row, ...]}.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

STATES = ("todo", "doing", "in_pr", "waiting_qa", "waiting_lu", "live", "blocked")
STATE_ZH = {"todo": "排队", "doing": "在做", "in_pr": "在 PR", "waiting_qa": "等 QA",
            "waiting_lu": "等你", "live": "已上线", "blocked": "卡住"}
MAX_ROWS = 30
KEEP_LIVE_H = 24   # finished rows stay a day so Lu sees them land, then drop off


class Board:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            self.data: dict[str, list[dict]] = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.path)

    def rows(self, channel: str, now: float | None = None) -> list[dict]:
        now = time.time() if now is None else now
        with self.lock:
            rows = self.data.get(channel, [])
            keep = [r for r in rows if not (r.get("state") == "live" and now - float(r.get("at") or 0) > KEEP_LIVE_H * 3600)]
            if len(keep) != len(rows):
                self.data[channel] = keep
                self._save()
            return [dict(r) for r in keep]

    def upsert(self, channel: str, by: str, id: int = 0, ask: str = "", state: str = "", who: str = "",
               due: str = "", link: str = "", note: str = "", msg: int = 0, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        state = (state or "").strip().lower().replace(" ", "_")
        if state and state not in STATES:
            raise ValueError(f"state must be one of {', '.join(STATES)}")
        with self.lock:
            rows = self.data.setdefault(channel, [])
            row = next((r for r in rows if int(r.get("id") or 0) == int(id or 0)), None) if id else None
            if row is None:
                if not ask.strip():
                    raise ValueError("a new row needs ask (what Lu asked for, in a few words)")
                if len(rows) >= MAX_ROWS:
                    raise ValueError(f"the board is full ({MAX_ROWS}); mark finished rows live or remove them")
                row = {"id": max([int(r.get("id") or 0) for r in rows] + [0]) + 1, "ask": "", "state": "todo",
                       "who": "", "due": "", "link": "", "note": "", "since": now}
                rows.append(row)
            for k, v in (("ask", ask), ("state", state), ("who", who), ("due", due), ("link", link), ("note", note)):
                if v:
                    row[k] = str(v).strip()[:200 if k != "ask" else 120]
            if msg and int(msg) > 0:
                row["msg"] = int(msg)
            row["at"] = now
            row["by"] = by
            self._save()
            return dict(row)

    def remove(self, channel: str, id: int) -> bool:
        with self.lock:
            rows = self.data.get(channel, [])
            n = len(rows)
            self.data[channel] = [r for r in rows if int(r.get("id") or 0) != int(id)]
            if len(self.data[channel]) != n:
                self._save()
                return True
            return False


def summary(rows: list[dict]) -> str:
    """'5 open · 2 在 PR · 1 等你' for the pinned strip."""
    open_rows = [r for r in rows if r.get("state") != "live"]
    counts: dict[str, int] = {}
    for r in open_rows:
        counts[r.get("state", "todo")] = counts.get(r.get("state", "todo"), 0) + 1
    parts = [f"{len(open_rows)} open"] + [f"{n} {STATE_ZH[s]}" for s in STATES if (n := counts.get(s)) and s != "live"]
    return " · ".join(parts)
