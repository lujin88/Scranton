"""Scranton: which projects Lu works on today.

Lu, 11-17: reminders went to five projects on a day she only worked on slides ("很多项目今天我根本
没有做，他反复去 tag 别人，那不是浪费我流量吗？… @ 之前先要问我一下"). So Scranton asks once a
day, and only the channels she names get reminders (stale rows, idle pokes, overdue work, the
catch-up). No answer yet means no reminders anywhere. She changes it with "@Scranton 今天做 …".
The day turns over at 05:00, so work she queued for the night keeps its reminders.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from safe_io import atomic_write

DAY_STARTS = 5          # 05:00 local
ALL = "全部项目"
NONE = "今天不做项目"
_ALL_RE = re.compile(r"全部|所有|都做|\ball\b", re.I)
_NONE_RE = re.compile(r"不做|都不|休息|安静|别提醒|不要提醒|停|\bnone\b", re.I)
_ADD_RE = re.compile(r"加上|再加|也做|还做|\badd\b", re.I)
MENTION_RE = re.compile(r"@scranton(?![\w-])", re.I)


def day_of(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime((time.time() if now is None else now) - DAY_STARTS * 3600))


class Today:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.s = {"day": "", "channels": [], "all": False, "asked": ""}
        try:
            self.s.update(json.loads(self.path.read_text("utf-8")))
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            atomic_write(self.path, json.dumps(self.s, ensure_ascii=False))
        except OSError:
            pass

    def answered(self, now: float | None = None) -> bool:
        return self.s.get("day") == day_of(now)

    def need_ask(self, now: float | None = None) -> bool:
        """True once per day, until asked. Marks it asked."""
        with self.lock:
            d = day_of(now)
            if self.s.get("asked") == d or self.s.get("day") == d:
                return False
            self.s["asked"] = d
            self._save()
            return True

    def choose(self, channels, all_: bool = False, add: bool = False, now: float | None = None) -> list[str]:
        with self.lock:
            d = day_of(now)
            cur = list(self.s.get("channels") or []) if (add and self.s.get("day") == d) else []
            for c in channels:
                if c not in cur:
                    cur.append(c)
            self.s.update({"day": d, "asked": d, "channels": cur,
                           "all": bool(all_) or (add and self.s.get("day") == d and bool(self.s.get("all")))})
            self._save()
            return cur

    def active(self, channel: str, now: float | None = None) -> bool:
        if not self.answered(now):
            return False
        return bool(self.s.get("all")) or channel in (self.s.get("channels") or [])

    def quiet(self, channels, now: float | None = None) -> set:
        return {c for c in channels if not self.active(c, now)}

    def chosen(self, now: float | None = None):
        """None = not answered today; else (all?, [channels])."""
        if not self.answered(now):
            return None
        return bool(self.s.get("all")), list(self.s.get("channels") or [])


def parse(text: str, channels) -> tuple[str, list[str]]:
    """What Lu meant: ("all" | "none" | "set" | "add" | "", [channels]). Channel names are matched
    longest first, so "contour" doesn't steal "contour-slide"."""
    t = MENTION_RE.sub(" ", str(text or "")).lower()
    found = []
    for c in sorted(channels, key=len, reverse=True):
        if c.lower() in t:
            found.append(c)
            t = t.replace(c.lower(), " ")
    if found:
        return ("add" if _ADD_RE.search(t) else "set"), [c for c in channels if c in found]
    if _ALL_RE.search(t):
        return "all", []
    if _NONE_RE.search(t):
        return "none", []
    return "", []


def question(owner: str, recent: list[str]) -> tuple[str, list[str]]:
    opts = recent[:4] + [ALL, NONE]
    return (f"@{owner} 今天做哪几个项目？点一个；要选多个，就在最后一行打字，例如「{'、'.join(recent[:2]) or '项目名'}」。"
            f"没选的项目今天不发提醒，也不为它 @ 任何人。之后想改，写「@Scranton 今天做 …」。", opts)


def confirm(kind: str, chans: list[str]) -> str:
    tail = "要改就写「@Scranton 今天做 …」或「@Scranton 加上 …」。"
    if kind == "all":
        return "好，今天所有项目都照常提醒。" + tail
    if kind == "none" or not chans:
        return "好，今天不发任何项目提醒，也不为项目 @ 人。" + tail
    return f"好，今天只做：{'、'.join(chans)}。其他项目不提醒、不 @ 人。" + tail


def help_text(state, channels) -> str:
    if state is None:
        cur = "今天还没选项目，所以现在不发任何提醒。"
    elif state[0]:
        cur = "今天：所有项目都提醒。"
    else:
        cur = f"今天只做：{'、'.join(state[1])}。" if state[1] else "今天不发项目提醒。"
    return (cur + " 可以这样写：「@Scranton 今天做 项目名、项目名」｜「@Scranton 加上 项目名」｜"
            "「@Scranton 全部」｜「@Scranton 今天不做」。项目名：" + "、".join(channels))
