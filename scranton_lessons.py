"""Lessons: what the owner keeps correcting in a project, written down once and handed to whoever
works there next.

Lu, 2026-11-19: "即便我一次性把所有要求都给到他们，他们也总是不按照我想要的来做，每次都要磨合很久。
有没有一个 learning 的机制，能让它不断去迭代优化呢？"

A model does not remember between sessions. What it "learns" is only what is written down and put
in front of it again. So the loop is:
  1. her corrections in a channel are already kept word for word (scranton_said)
  2. once a day a teammate turns them into short preferences and proposes them (chat_lessons)
  3. she keeps or drops each one: nothing takes effect without her
  4. kept ones are handed to every teammate who reads that channel (chat_read)
At most MAX_KEPT per project: a long list is not read, it is skimmed (the 16,000-character brief
taught that). A new one past the cap pushes the oldest out.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

MAX_KEPT = 15
MAX_PENDING = 6
MIN_CORRECTIONS = 3          # fewer than this in a day: nothing to learn from yet
MAX_LEN = 140
CORRECTION_RE = re.compile(
    r"不是|不对|错了|搞错|理解错|我说过|说过了|讲过|怎么又|又是|还是没|怎么还|为什么|为啥|不要|别再|别用|太大|太小|太多|太挤|太丑|丑|难看|"
    r"不好看|对齐|字号|字体|间距|跳来跳去|不像|没有按|没按|不一样|重新|重做|无法接受", re.I)


def is_correction(text: str) -> bool:
    return bool(CORRECTION_RE.search(text or ""))


def _norm(t: str) -> str:
    return re.sub(r"[\s，。,.;；:：、!！?？\"'「」]+", "", t or "").lower()


class Lessons:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            self.data: dict = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.path)

    def _ch(self, ch: str) -> dict:
        return self.data.setdefault(ch, {"kept": [], "pending": [], "ran": 0, "seq": 0, "ver": 0})

    def get(self, ch: str) -> dict:
        with self.lock:
            c = self.data.get(ch) or {}
            return {"kept": list(c.get("kept", [])), "pending": list(c.get("pending", [])), "ver": c.get("ver", 0)}

    def propose(self, ch: str, texts: list[str], by: str = "", now: float | None = None) -> list[dict]:
        """Add proposals (short lines). Ones already kept or pending are skipped."""
        now = time.time() if now is None else now
        added = []
        with self.lock:
            c = self._ch(ch)
            have = {_norm(x["text"]) for x in c["kept"] + c["pending"]}
            for t in texts:
                t = re.sub(r"^\s*(?:[-*•]|\d+[.、)])\s*", "", str(t or "")).strip()[:MAX_LEN]
                if len(t) < 4 or _norm(t) in have or len(c["pending"]) >= MAX_PENDING:
                    continue
                c["seq"] += 1
                item = {"id": c["seq"], "text": t, "by": by, "at": now}
                c["pending"].append(item)
                have.add(_norm(t))
                added.append(item)
            if added:
                self._save()
        return added

    def decide(self, ch: str, lid: int, keep: bool, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self.lock:
            c = self._ch(ch)
            item = next((x for x in c["pending"] if x["id"] == int(lid)), None)
            if item is None:
                return False
            c["pending"].remove(item)
            if keep:
                c["kept"].append({**item, "kept_at": now})
                c["kept"] = c["kept"][-MAX_KEPT:]
                c["ver"] += 1
            self._save()
            return True

    def add(self, ch: str, text: str, now: float | None = None) -> dict | None:
        """One she writes herself: kept at once."""
        got = self.propose(ch, [text], by="Lu", now=now)
        if not got:
            return None
        self.decide(ch, got[0]["id"], True, now)
        return got[0]

    def remove(self, ch: str, lid: int) -> bool:
        with self.lock:
            c = self._ch(ch)
            n = len(c["kept"])
            c["kept"] = [x for x in c["kept"] if x["id"] != int(lid)]
            if len(c["kept"]) == n:
                return False
            c["ver"] += 1
            self._save()
            return True

    def drop_channel(self, ch: str) -> None:
        with self.lock:
            if self.data.pop(ch, None) is not None:
                self._save()

    def text_for(self, ch: str) -> str:
        """What a teammate reading this channel is handed."""
        with self.lock:
            kept = list((self.data.get(ch) or {}).get("kept", []))
        if not kept:
            return ""
        lines = "\n".join(f"{i}. {x['text']}" for i, x in enumerate(kept, 1))
        return (f"[Lu 对 #{ch} 这个项目的偏好，都是她纠正过的事。动手前读一遍，交之前逐条对照；"
                f"哪条做不到，在交付里说明是哪条、为什么]\n{lines}")

    def due(self, ch: str, day: str) -> bool:
        with self.lock:
            return (self.data.get(ch) or {}).get("ran_day") != day

    def mark_ran(self, ch: str, day: str) -> None:
        with self.lock:
            self._ch(ch)["ran_day"] = day
            self._save()


def request_text(ch: str, items: list[dict], kept: list[dict], handle: str) -> str:
    """Asks a teammate to turn a day's corrections into at most 3 short preferences."""
    said = "\n".join(f"· #{it['id']} {str(it.get('text') or '')[:180]}" for it in items[-25:])
    have = "\n".join(f"· {x['text']}" for x in kept) or "（还没有）"
    return (f"@{handle} 学习任务，只做这一件，不要改任何文件。下面是 Lu 昨天在这个项目里纠正团队的原话。"
            f"把其中会再次发生的归纳成最多 3 条「偏好」：每条一句话、30 字以内、写成做事的人能直接照做的样子"
            f"（例：主视觉不用缩小的界面截图；每页标题的位置和字号一致）。只针对某一页某一次的不要写，已有的不要重复。"
            f"没有值得归纳的就回「没有」。用 chat_lessons(action=\"propose\", channel=\"{ch}\", lessons=\"一行一条\") 提交，"
            f"Lu 确认后才生效。\n已有的偏好：\n{have}\nLu 的原话：\n{said}")
