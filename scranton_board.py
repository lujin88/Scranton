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


STALE_H = 4          # a row nobody touched for this long is probably out of date
MAX_PER_PERSON = 5   # Lu, 11-12: one person holding 11 of 25 is the bottleneck


def housekeeping(board: "Board", pr_state, now: float | None = None) -> dict[str, dict]:
    """Per channel: rows whose PR has merged (set live here) and what to tell the project manager:
    {channel: {"merged": [row], "stale": [row], "overloaded": {who: n}}}. Each stale row is
    reported once per STALE_H window. pr_state(url) -> "MERGED" / "OPEN" / "CLOSED" / None."""
    now = time.time() if now is None else now
    out: dict[str, dict] = {}
    with board.lock:
        changed = False
        for ch, rows in board.data.items():
            rep = {"merged": [], "stale": [], "overloaded": {}}
            counts: dict[str, int] = {}
            for r in rows:
                if r.get("state") == "live":
                    continue
                link = str(r.get("link") or "")
                if "/pull/" in link:
                    try:
                        st = pr_state(link)
                    except Exception:
                        st = None
                    if st == "MERGED":
                        r["state"], r["at"], r["by"], r["note"] = "live", now, "Scranton", "PR merged"
                        rep["merged"].append(dict(r))
                        changed = True
                        continue
                if r.get("who"):
                    counts[r["who"]] = counts.get(r["who"], 0) + 1
                last = max(float(r.get("at") or 0), float(r.get("nudged") or 0))
                if now - last > STALE_H * 3600:
                    r["nudged"] = now
                    rep["stale"].append(dict(r))
                    changed = True
            # once per person per STALE_H window (11-12: "法务 8 件" went out 7 times in an afternoon)
            told = board.__dict__.setdefault("_told_over", {})
            rep["overloaded"] = {}
            for w, n in counts.items():
                k = f"{ch}:{w}"
                if n > MAX_PER_PERSON and now - told.get(k, 0) > STALE_H * 3600:
                    told[k] = now
                    rep["overloaded"][w] = n
            if rep["merged"] or rep["stale"] or rep["overloaded"]:
                out[ch] = rep
        if changed:
            board._save()
    return out


def nudge_text(rep: dict, label=lambda h: h) -> str:
    """One message to the project manager about a channel's board."""
    lines = []
    if rep["stale"]:
        hrs = lambda r: int((time.time() - float(r.get("at") or 0)) // 3600)
        lines.append(f"@pm Your asks 里有 {len(rep['stale'])} 行超过 {STALE_H} 小时没更新，按实际改一下（没在做就写 todo，卡住写 blocked + note）：")
        lines += [f"· #{r['id']} {r.get('ask', '')[:40]}（{label(r.get('who', '')) or '没人'}，{hrs(r)} 小时）" for r in rep["stale"][:8]]
        if len(rep["stale"]) > 8:
            lines.append(f"· 还有 {len(rep['stale']) - 8} 行")
    if rep.get("overloaded"):
        lines.append("超过 5 件的人，把没开始的转给别人：" + "，".join(f"{label(w)} {n} 件" for w, n in rep["overloaded"].items()))
    return "\n".join(lines)
