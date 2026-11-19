"""Scranton: what Lu said, kept by Scranton instead of by the project manager's memory.

Lu, 11-18: "PM 总是理解错我的意思，每次说完很多事情都没做。我不是用 Notion 记录了么". On 11-17 she
gave 424 instructions in one channel; the PM wrote 41 Notion rows, none after 16:05, and only when
she asked. Its memory is a context window that gets compacted, so "我昨天说过了" was true and lost.

So every instruction she sends is kept here the moment she sends it: her words, her pictures, the
message id, what she was replying to. A teammate "takes" one by citing its number (#15247) or
replying to it, which they already do. What nobody took is listed for the PM, and `find` gives
anyone everything she ever said about a page before they touch it. No model call anywhere.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from safe_io import atomic_write

KEEP_DAYS = 14
MIN_CHARS = 6             # Chinese is dense: 「这页小字删掉」 is an instruction
OPEN_AFTER = 15 * 60        # an instruction nobody took for this long is worth a note
NOTE_EVERY = 45 * 60        # one note per channel at most this often
_CLICK_RE = re.compile(r"^[A-Fa-f1-9]{1,2}\s*[：:]")
_ID_RE = re.compile(r"#(\d{3,7})(?!\d)")


def body_of(text: str) -> str:
    """Her own words: without the quoted lines ("> …") and the @handles."""
    lines = [l for l in str(text or "").split("\n") if not l.lstrip().startswith(">")]
    return re.sub(r"@[\w-]+", "", "\n".join(lines)).strip()


def is_instruction(text: str) -> bool:
    b = body_of(text)
    return len(b) >= MIN_CHARS and not _CLICK_RE.match(b)


_DO_RE = re.compile(r"[把改换删加做移调放挪缩去留用写画补修重]|\b(?:make|change|move|remove|add|fix|use|delete)\b", re.I)


def is_question(text: str) -> bool:
    """「为什么实习生又 stop 了？」「这个做完了吗？」: she wants an answer, not a change. An answer
    from the project manager settles it. Anything that asks for a change is an instruction."""
    b = body_of(text)
    return bool(re.search(r"[?？]|吗|为什么|怎么回事|什么情况", b)) and len(b) <= 60 and not _DO_RE.search(b)


def cited_ids(text: str) -> list[int]:
    return [int(x) for x in _ID_RE.findall(str(text or ""))]


class Said:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.items: dict[str, dict] = {}
        self.noted: dict[str, float] = {}
        try:
            d = json.loads(self.path.read_text("utf-8"))
            self.items = d.get("items") or {}
            self.noted = d.get("noted") or {}
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            atomic_write(self.path, json.dumps({"items": self.items, "noted": self.noted}, ensure_ascii=False))
        except OSError:
            pass

    def add(self, msg: dict, context: str = "", state: str = "open") -> bool:
        """Keep one of Lu's messages. `context`: the start of the message she replied to."""
        mid = msg.get("id")
        if not isinstance(mid, int) or not is_instruction(msg.get("text")):
            return False
        with self.lock:
            if str(mid) in self.items:
                return False
            atts = [a.get("url") for a in (msg.get("attachments") or []) if isinstance(a, dict) and a.get("url")]
            self.items[str(mid)] = {"id": mid, "ch": msg.get("channel") or "general", "ts": float(msg.get("timestamp") or time.time()),
                                    "text": str(msg.get("text") or ""), "atts": atts, "ctx": str(context or "")[:240],
                                    "state": state, "by": "", "ref": 0, "note": ""}
            cut = time.time() - KEEP_DAYS * 86400
            for k in [k for k, v in self.items.items() if v["ts"] < cut]:
                del self.items[k]
            self._save()
            return True

    def backfill(self, msgs, owner: str, by_id=None) -> int:
        """First start: what she said in the last KEEP_DAYS becomes findable. Marked "old", so
        nobody is chased for it."""
        cut, n = time.time() - KEEP_DAYS * 86400, 0
        with self.lock:
            for m in msgs:
                mid = m.get("id")
                if (not isinstance(mid, int) or str(mid) in self.items or float(m.get("timestamp") or 0) < cut
                        or str(m.get("sender") or "").lower() != owner.lower() or m.get("type") not in ("chat", None)
                        or str(m.get("channel") or "").startswith("dm-scranton") or not is_instruction(m.get("text"))):
                    continue
                o = by_id(m.get("reply_to")) if (by_id and isinstance(m.get("reply_to"), int)) else None
                atts = [a.get("url") for a in (m.get("attachments") or []) if isinstance(a, dict) and a.get("url")]
                self.items[str(mid)] = {"id": mid, "ch": m.get("channel") or "general", "ts": float(m.get("timestamp") or 0),
                                        "text": str(m.get("text") or ""), "atts": atts,
                                        "ctx": (f"{o.get('sender')}: {o.get('text')}" if o else "")[:240],
                                        "state": "old", "by": "", "ref": 0, "note": ""}
                n += 1
            if n:
                self._save()
        return n

    def get(self, mid) -> dict | None:
        with self.lock:
            it = self.items.get(str(mid))
            return dict(it) if it else None

    def take(self, ids, by: str, ref: int = 0) -> list[int]:
        """Someone picked these up (cited the number, or replied to it)."""
        done = []
        with self.lock:
            for i in ids:
                it = self.items.get(str(i))
                if it and it["state"] == "open":
                    it.update(state="taken", by=by, ref=int(ref or 0))
                    done.append(int(i))
            if done:
                self._save()
        return done

    # ---- acceptance (Lu, 2026-11-19): "taken" says someone picked it up, not that it was done,
    # and not that it was done the way she said. A result shown for one of her instructions
    # waits for her verdict; nothing is finished until she says it is right.
    CHECK_DAYS = 4

    def mark_done(self, ids, msg_id: int, by: str, now: float | None = None) -> list[int]:
        """A teammate showed a result (a message with a picture) for these instructions."""
        now = time.time() if now is None else now
        hit = []
        with self.lock:
            for i in ids:
                it = self.items.get(str(i))
                if not it or it["state"] in ("skipped", "old") or it.get("verdict") == "ok" or not is_instruction(it["text"]):
                    continue
                if it["state"] == "open":
                    it.update(state="taken", by=by, ref=int(msg_id or 0))
                it.update(done_msg=int(msg_id), done_by=by, done_ts=now)
                it.pop("verdict", None)
                hit.append(int(i))
            if hit:
                self._save()
        return hit

    def verdict(self, mid, ok: bool, note: str = "") -> dict | None:
        """Her answer to a result. Right: finished. Not right: back to work, one more round counted."""
        with self.lock:
            it = self.items.get(str(mid))
            if not it or not it.get("done_msg"):
                return None
            it.setdefault("judged_ts", time.time())
            if ok:
                it["verdict"] = "ok"
            else:
                it["rounds"] = int(it.get("rounds") or 0) + 1
                it["last_no"] = {"msg": it.pop("done_msg"), "by": it.pop("done_by", ""), "note": str(note or "")[:300]}
                it.pop("done_ts", None)
                it.pop("verdict", None)
            self._save()
            return dict(it)

    def accept_result(self, msg_id: int) -> list[int]:
        """Her thumbs-up on the result itself accepts everything it was shown for."""
        with self.lock:
            hit = [int(k) for k, it in self.items.items() if it.get("done_msg") == int(msg_id) and it.get("verdict") != "ok"]
            for k in hit:
                self.items[str(k)]["verdict"] = "ok"
                self.items[str(k)].setdefault("judged_ts", time.time())
            if hit:
                self._save()
        return hit

    def pending_for(self, channel: str, exclude=()) -> list[dict]:
        """Her instructions someone took in this channel that no result has been shown for yet."""
        skip = {int(i) for i in exclude}
        with self.lock:
            out = [dict(v) for v in self.items.values()
                   if v["ch"] == channel and v["state"] == "taken" and not v.get("done_msg") and v.get("verdict") != "ok"
                   and v["id"] not in skip and is_instruction(v["text"]) and time.time() - v["ts"] < self.CHECK_DAYS * 86400]
        return sorted(out, key=lambda v: v["ts"])

    def first_time(self, days: int = 7, now: float | None = None) -> dict:
        """Of the results she judged in the period, how many were right the first time she saw them.
        Counted per instruction; by whoever showed the result."""
        now = time.time() if now is None else now
        who: dict[str, list[int]] = {}
        with self.lock:
            for v in self.items.values():
                if not v.get("judged_ts") or now - float(v["judged_ts"]) > days * 86400:
                    continue
                by = re.sub(r"-\d+$", "", str(v.get("done_by") or (v.get("last_no") or {}).get("by") or "").lower()) or "?"
                w = who.setdefault(by, [0, 0])
                w[0] += 1
                w[1] += 1 if v.get("verdict") == "ok" and not v.get("rounds") else 0
        return {"judged": sum(w[0] for w in who.values()), "first": sum(w[1] for w in who.values()),
                "by": sorted(({"who": k, "judged": w[0], "first": w[1]} for k, w in who.items()), key=lambda x: -x["judged"])}

    def to_check(self, channel: str = "", now: float | None = None) -> list[dict]:
        """Results waiting for her verdict, oldest first."""
        now = time.time() if now is None else now
        with self.lock:
            out = [dict(v) for v in self.items.values()
                   if v.get("done_msg") and not v.get("verdict") and (not channel or v["ch"] == channel)
                   and now - float(v.get("done_ts") or 0) < self.CHECK_DAYS * 86400]
        return sorted(out, key=lambda v: v.get("done_ts") or 0)

    def skip(self, ids, by: str, note: str) -> list[int]:
        done = []
        with self.lock:
            for i in ids:
                it = self.items.get(str(i))
                if it and it["state"] == "open":
                    it.update(state="skipped", by=by, note=str(note or "")[:200])
                    done.append(int(i))
            if done:
                self._save()
        return done

    def open_items(self, channel: str = "", older_than: float = 0, now: float | None = None) -> list[dict]:
        now = time.time() if now is None else now
        with self.lock:
            out = [dict(v) for v in self.items.values()
                   if v["state"] == "open" and (not channel or v["ch"] == channel) and now - v["ts"] >= older_than]
        return sorted(out, key=lambda v: v["ts"])

    def find(self, channel: str, q: str, limit: int = 20) -> list[dict]:
        """Everything Lu said in this channel that mentions every word of `q` (her words, or what
        she was replying to). Oldest first, so the latest word on a page is the last line."""
        words = [w for w in re.split(r"[\s,，、]+", str(q or "").lower()) if w]
        with self.lock:
            pool = [dict(v) for v in self.items.values() if not channel or v["ch"] == channel]
        hit = [v for v in pool if all(w in (v["text"] + " " + v["ctx"]).lower() for w in words)]
        return sorted(hit, key=lambda v: v["ts"])[-limit:]

    def counts(self, channel: str) -> dict:
        with self.lock:
            vs = [v for v in self.items.values() if v["ch"] == channel]
        day = time.time() - 86400
        return {"open": sum(v["state"] == "open" for v in vs),
                "today": sum(v["ts"] >= day for v in vs),
                "skipped": sum(v["state"] == "skipped" and v["ts"] >= day for v in vs)}

    def due_note(self, channel: str, now: float | None = None):
        """The open ones worth telling the PM about now, or []. Marks the channel as told."""
        now = time.time() if now is None else now
        items = self.open_items(channel, OPEN_AFTER, now)
        if not items or now - float(self.noted.get(channel) or 0) < NOTE_EVERY:
            return []
        with self.lock:
            self.noted[channel] = now
            self._save()
        return items


def short(it: dict, n: int = 46) -> str:
    b = re.sub(r"\s+", " ", body_of(it["text"]))
    return f"#{it['id']} {time.strftime('%H:%M', time.localtime(it['ts']))}「{b[:n]}{'…' if len(b) > n else ''}」" + ("（有图）" if it.get("atts") else "")


def note_text(owner: str, items: list[dict], via: str = "pm") -> str:
    lines = "\n".join("· " + short(it) for it in items[:8])
    more = f"\n（还有 {len(items) - 8} 条，用 chat_said(action=\"open\") 看全）" if len(items) > 8 else ""
    return (f"@{via} {owner} 说的这 {len(items)} 条还没人接：\n{lines}{more}\n"
            f"每条二选一：派出去（派活那条里写上它的 #号，Scranton 就记为已接），或 chat_said(action=\"skip\", ids=[…], note=\"为什么不做\")。"
            f"不用回 {owner}，也不用回我。")


def line(it: dict) -> dict:
    return {"id": it["id"], "at": time.strftime("%m-%d %H:%M", time.localtime(it["ts"])), "said": it["text"],
            "replying_to": it["ctx"], "pictures": it["atts"], "state": it["state"], "by": it["by"], "note": it["note"]}
