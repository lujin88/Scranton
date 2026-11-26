"""接回 (Lu, 11-26, after Lauren Tan's "catch me up on everything since my last message, and if
there are action items give me enough context to make a call"). Lu runs many projects at once; the
cost of coming back to a channel is remembering where it stood. One click: what happened since she
last spoke here, and what is waiting for her, with enough background to decide.

The facts come from the chat and the board (no model needed). The project manager only writes
the background for the items she has to decide."""
from __future__ import annotations

import time

SKIP_RECENT = 15 * 60     # her messages from the last 15 min are "now", not "last time"
NO_ANCHOR_HOURS = 24      # never spoke here: look at the last day
COOLDOWN = 120            # a second click within 2 min does nothing
MAX_ROWS = 8
DONE_STATES = ("live",)
OPEN_FOR_HER = ("waiting_lu",)


def _hers(m: dict, owner: str) -> bool:
    if str(m.get("sender") or "").lower() != owner.lower():
        return False
    if (m.get("metadata") or {}).get("via"):          # sent for her by another tool: she didn't type it
        return False
    return not str(m.get("text") or "").startswith("/")


def anchor(msgs: list[dict], owner: str, now: float | None = None) -> dict | None:
    """Her last message in this channel before this visit."""
    now = time.time() if now is None else now
    for m in sorted(msgs, key=lambda m: -float(m.get("timestamp") or 0)):
        if _hers(m, owner) and now - float(m.get("timestamp") or 0) > SKIP_RECENT:
            return m
    return None


def gather(msgs: list[dict], rows: list[dict], owner: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    a = anchor(msgs, owner, now)
    since = float(a.get("timestamp") or 0) if a else now - NO_ANCHOR_HOURS * 3600
    after = [m for m in msgs if float(m.get("timestamp") or 0) > since and not _hers(m, owner)
             and str(m.get("sender") or "").lower() not in ("system",) and m.get("type", "chat") == "chat"]
    changed = [r for r in rows if float(r.get("at") or 0) > since]
    return {"anchor": a, "since": since, "messages": len(after),
            "done": [r for r in changed if r.get("state") in DONE_STATES],
            "moving": [r for r in changed if r.get("state") not in DONE_STATES + OPEN_FOR_HER + ("later",)],
            "for_her": [r for r in rows if r.get("state") in OPEN_FOR_HER]}


def nothing(info: dict) -> bool:
    return not info["messages"] and not info["done"] and not info["moving"] and not info["for_her"]


def _row(r: dict) -> str:
    who = f"，{r.get('who')}" if r.get("who") else ""
    return f"行 {r.get('id')}「{str(r.get('ask') or '')[:40]}」{who}"


def _rows(rows: list[dict]) -> str:
    if not rows:
        return "没有"
    more = f"；另有 {len(rows) - MAX_ROWS} 行" if len(rows) > MAX_ROWS else ""
    return "；".join(_row(r) for r in rows[:MAX_ROWS]) + more


def when_text(info: dict) -> str:
    a = info["anchor"]
    if not a:
        return f"Lu 最近没在这里说过话，按过去 {NO_ANCHOR_HOURS} 小时算"
    return "Lu 上次在这里说话是 " + time.strftime("%m-%d %H:%M", time.localtime(info["since"])) + f"（#{a.get('id')}）"


def request_text(to: str, info: dict) -> str:
    return (f"@{to} 接回｜{when_text(info)}，之后 {info['messages']} 条消息。只回她一条，回在这条下面，不派活、不 @ 别人。\n"
            f"① 做完了什么：每项一行，带 PR 号或消息号；有进展没做完的写到哪了。看板：上线 {_rows(info['done'])}；在动 {_rows(info['moving'])}。\n"
            f"② 等她定的：每项两句背景（是什么、卡在哪）＋A/B/C，你倾向的放第一个，最多 5 项，其余写数量。看板「等你」：{_rows(info['for_her'])}。\n"
            f"要她合并的 PR 只写卡片在哪条消息。没有就写「没有」。")


def quiet_text(info: dict) -> str:
    return f"接回：{when_text(info)}。之后这里没有新消息，看板没有变化，也没有等你定的事。"
