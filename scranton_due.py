"""Who owes what by when (Lu, 11-11: she asked "还没做完吗 / 在干活吗" 14 times in 16 hours).

When the project manager (or Lu) hands someone work, the message ends with "交 HH:MM". We keep
that per teammate, show it next to "X is working", and when it passes with nothing delivered we
tell the project manager once, so chasing is the PM's job, not Lu's.

Delivered = the teammate wrote something real in that channel after being asked (not just a
"收到", which is short), or a new due time replaced the old one.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

DUE_RE = re.compile(r"(?:交|due|deliver(?:y)?|ETA)\s*[:：]?\s*(?:by\s*)?([01]?\d|2[0-3])[:：]([0-5]\d)", re.I)
DUE_BEFORE_RE = re.compile(r"([01]?\d|2[0-3])[:：]([0-5]\d)\s*(?:前|之前)\s*交")
MENTION_RE = re.compile(r"@([A-Za-z0-9_-]+)")
ACK_MAX = 40   # a reply this short is "收到", not a delivery
DELIVERED_RE = re.compile(r"已交|交了|交付|已完成|做完了|done|delivered|https?://|PR\s*#?\d", re.I)


def parse_due(text: str, now: float | None = None) -> float | None:
    """Epoch of the 'HH:MM' in '交 HH:MM' / 'HH:MM 前交', today or (if already past) tomorrow."""
    m = DUE_RE.search(text or "") or DUE_BEFORE_RE.search(text or "")
    if not m:
        return None
    now = time.time() if now is None else now
    lt = time.localtime(now)
    t = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, int(m.group(1)), int(m.group(2)), 0, 0, 0, -1))
    if t < now - 15 * 60:   # "交 09:00" said at 23:30 means tomorrow morning
        t += 24 * 3600
    return t


class DueBook:
    def __init__(self, path: Path, assigners: tuple[str, ...] = ("pm",)):
        self.path = Path(path)
        self.assigners = {a.lower() for a in assigners}
        try:
            self.items: dict[str, dict] = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.items = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.items, ensure_ascii=False), "utf-8")
        except OSError:
            pass

    def note(self, msg: dict, agents: set[str], owner: str = "lu", now: float | None = None) -> bool:
        """Read one chat message. True when something changed."""
        if (msg.get("type") or "chat") != "chat":
            return False
        now = float(msg.get("timestamp") or (time.time() if now is None else now))
        sender = str(msg.get("sender") or "")
        base = sender.lower().split("-")[0] if sender.lower() not in agents else sender.lower()
        text = str(msg.get("text") or "")
        channel = str(msg.get("channel") or "general")
        changed = False
        # 1. a delivery clears that teammate's due in this channel
        it = self.items.get(base)
        if it and it.get("channel") == channel and now > float(it.get("at") or 0):
            if len(text.strip()) > ACK_MAX or DELIVERED_RE.search(text) or msg.get("attachments"):
                self.items.pop(base, None)
                changed = True
        # 2. an assignment with a due time
        if base in self.assigners or sender.lower() == owner.lower():
            due = parse_due(text, now)
            if due:
                for h in {m.lower() for m in MENTION_RE.findall(text)} & agents:
                    if h == base:
                        continue
                    self.items[h] = {"due": due, "channel": channel, "id": msg.get("id"), "at": now,
                                     "by": base, "told": False}
                    changed = True
        if changed:
            self._save()
        return changed

    def overdue(self, now: float | None = None, grace: float = 120) -> list[tuple[str, dict]]:
        """Teammates past their time, not yet told to the PM. Marks them told."""
        now = time.time() if now is None else now
        out = []
        for h, it in self.items.items():
            if not it.get("told") and now > float(it["due"]) + grace:
                it["told"] = True
                out.append((h, it))
        if out:
            self._save()
        return out

    def drop(self, handle: str) -> None:
        if self.items.pop(handle, None) is not None:
            self._save()

    def public(self) -> dict:
        return {h: {"due": it["due"], "channel": it["channel"], "id": it.get("id")} for h, it in self.items.items()}
