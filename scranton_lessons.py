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
MIN_CORRECTIONS = 2          # Lu, 11-23: the same kind of thing said twice within a week is enough
WINDOW_DAYS = 7              # was one day: corrections spread over several days never reached three
MAX_EVERYWHERE = 8           # preferences that go to every project: a short list, or it is skimmed
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

    def propose(self, ch: str, texts: list[str], by: str = "", now: float | None = None, need_source: bool = True) -> list[dict]:
        """Add proposals (short lines). Ones already kept or pending are skipped."""
        now = time.time() if now is None else now
        added = []
        with self.lock:
            c = self._ch(ch)
            have = {_norm(x["text"]) for x in c["kept"] + c["pending"]}
            for t in texts:
                t = re.sub(r"^\s*(?:[-*•]|\d+[.、)])\s*", "", str(t or "")).strip()
                # the messages it was drawn from ("…（#18127 #18136）"): kept apart, so she can see them
                src = [int(x) for x in re.findall(r"#(\d{3,7})", t)][:6]
                t = re.sub(r"[（(]?\s*(?:#\d{3,7}[\s,，、]*)+[)）]?\s*$", "", t).strip()[:MAX_LEN]
                if not src and need_source:
                    continue    # no source, no proposal: she cannot judge a rule without her own words beside it
                if len(t) < 4 or _norm(t) in have or len(c["pending"]) >= MAX_PENDING:
                    continue
                c["seq"] += 1
                item = {"id": c["seq"], "text": t, "by": by, "at": now, "from": src}
                c["pending"].append(item)
                have.add(_norm(t))
                added.append(item)
            if added:
                self._save()
        return added

    def drop_unsourced(self) -> list[str]:
        """Proposals made before sources were required: take them out and let that project be
        asked again today. Returns the channels touched."""
        out = []
        with self.lock:
            for ch, c in self.data.items():
                keep = [x for x in c.get("pending", []) if x.get("from")]
                if len(keep) != len(c.get("pending", [])):
                    c["pending"] = keep
                    c.pop("ran_day", None)
                    out.append(ch)
            if out:
                self._save()
        return out

    def set_batch(self, ch: str, ids: list[int]) -> None:
        """The corrections a request was made from: the source of proposals that name none."""
        with self.lock:
            c = self._ch(ch)
            c["batch"] = [int(i) for i in ids][-25:]
            c["asked"] = (list(c.get("asked", [])) + [int(i) for i in ids])[-300:]   # not asked about twice
            self._save()

    def asked(self, ch: str) -> set[int]:
        with self.lock:
            return set((self.data.get(ch) or {}).get("asked", []))

    def everywhere(self, ch: str, lid: int, on: bool) -> bool:
        """A kept preference that holds in every project ("show the whole page, not the first
        screen"), not only where she first said it. At most MAX_EVERYWHERE in all."""
        with self.lock:
            item = next((x for x in self._ch(ch)["kept"] if x["id"] == int(lid)), None)
            if item is None:
                return False
            if on and not item.get("all"):
                n = sum(1 for c in self.data.values() for x in c.get("kept", []) if x.get("all"))
                if n >= MAX_EVERYWHERE:
                    return False
            item["all"] = bool(on)
            for c in self.data.values():
                c["ver"] = int(c.get("ver", 0)) + 1
            self._save()
            return True

    def decide(self, ch: str, lid: int, keep: bool, now: float | None = None, text: str = "") -> bool:
        now = time.time() if now is None else now
        with self.lock:
            c = self._ch(ch)
            item = next((x for x in c["pending"] if x["id"] == int(lid)), None)
            if item is None:
                return False
            c["pending"].remove(item)
            if keep:
                if str(text or "").strip():          # she reworded it before keeping
                    item = {**item, "text": str(text).strip()[:MAX_LEN]}
                c["kept"].append({**item, "kept_at": now})
                c["kept"] = c["kept"][-MAX_KEPT:]
                c["ver"] += 1
            self._save()
            return True

    def add(self, ch: str, text: str, now: float | None = None) -> dict | None:
        """One she writes herself: kept at once."""
        got = self.propose(ch, [text], by="Lu", now=now, need_source=False)
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
            have = {_norm(x["text"]) for x in kept}
            for other, c in self.data.items():      # the ones she marked for every project
                for x in c.get("kept", []) if other != ch else []:
                    if x.get("all") and _norm(x["text"]) not in have:
                        kept.append(x)
                        have.add(_norm(x["text"]))
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
    # Her words are quoted, so their @names must not wake anyone (11-20 07:03: this note woke the
    # visual designer, the visual checker, motion and the developer, who each replied "not for me").
    said = "\n".join(f"· #{it['id']} {re.sub(r'@(?=[A-Za-z])', '', str(it.get('text') or ''))[:180]}" for it in items[-25:])
    have = "\n".join(f"· {x['text']}" for x in kept) or "（还没有）"
    return (f"@{handle} 学习任务，只做这一件，不要改任何文件。下面是 Lu 最近 7 天在这个项目里纠正团队的原话。"
            f"只归纳她说过两次以上的同一类问题（说过一次的不算），归纳成最多 3 条「偏好」：每条一句话、规则本身 30 字以内、写成做事的人能直接照做的样子"
            f"（例：主视觉不用缩小的界面截图；每页标题的位置和字号一致）。每条后面用「，因为…」带上原因：Lu 说过原因就用她的，没说过就写你推测的并标「（原因是推测）」，让她确认时改。只针对某一页某一次的不要写，已有的不要重复。"
            f"每条末尾必须写上它出自哪几条原话的编号，例如「（#18127 #18136）」：Lu 要对照自己的原话才能判断，没写编号的那条不会被收下。没有值得归纳的就回「没有」。用 chat_lessons(action=\"propose\", channel=\"{ch}\", lessons=\"一行一条\") 提交，"
            f"Lu 确认后才生效。\n已有的偏好：\n{have}\nLu 的原话：\n{said}")
