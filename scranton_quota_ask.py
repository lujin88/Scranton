"""Ask Lu before a plan runs out (Lu, 11-11: "到 98% 就可以开始问了：我已经到 98% 了，然后怎么做？
可以先用 API，API 不行再换模型。时间长度要结合它重置的时间点").

Pure logic here; app.py posts the question, applies the pick and puts things back after the reset.
State lives in data/quota_ask.json:
  asked:    {provider: resets}            one question per plan window
  approved: {provider: {"until", "then"}} Lu picked "API first": the key is allowed until the reset,
                                          and if the key fails, `then` (another app) takes over
  moved:    {teammate: {"command", "model", "until"}}  what to put back after the reset
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ASK_AT = 98.0
APP_NAMES = {"claude": "Claude", "codex": "ChatGPT", "cursor": "Cursor", "gemini": "Gemini"}
STANDIN_MODEL = {"cursor": "composer-2.5", "codex": "", "claude": ""}
WAIT_IF_WITHIN_H = 1.0     # resets within an hour: waiting is cheapest
API_UP_TO_H = 24.0         # longer than a day on pay-per-use gets expensive: suggest another app


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            d = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            d = {}
        self.asked: dict = d.get("asked") or {}
        self.approved: dict = d.get("approved") or {}
        self.moved: dict = d.get("moved") or {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"asked": self.asked, "approved": self.approved, "moved": self.moved},
                                        ensure_ascii=False, indent=1), "utf-8")

    def api_ok(self, provider: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        a = self.approved.get(provider) or {}
        return a.get("mode") == "api" and now < float(a.get("until") or 0)


def standin(provider: str, usage_of) -> tuple[str, float] | None:
    """The other app with the most room: (provider, % used). usage_of(provider, model) -> dict|None."""
    best = None
    for p in ("cursor", "codex", "claude"):
        if p == provider:
            continue
        u = usage_of(p, STANDIN_MODEL.get(p, ""))
        if not u or u["pct"] >= 90:
            continue
        if best is None or u["pct"] < best[1]:
            best = (p, float(u["pct"]))
    return best


def question(provider: str, pct: float, resets: float | None, who: list[str], has_key: bool,
             other: tuple[str, float] | None, owner: str = "Lu", now: float | None = None) -> tuple[str, list[str]] | None:
    """(text, choices) for Lu, the team's pick first and marked 推荐. None when there's nothing to choose."""
    now = time.time() if now is None else now
    app = APP_NAMES.get(provider, provider)
    hours = max(0.0, (float(resets) - now) / 3600) if resets else None
    when = time.strftime("%m-%d %H:%M", time.localtime(float(resets))) if resets else "未知"
    left = (f"还有 {hours:.0f} 小时" if hours >= 1 else f"还有 {hours * 60:.0f} 分钟") if hours is not None else "重置时间未知"
    other_txt = (f"{APP_NAMES[other[0]]}（{'Composer 2.5，' if other[0] == 'cursor' else ''}已用 {other[1]:.0f}%）"
                 if other else None)
    wait = f"等重置（{when}），这期间他们停下"
    api = ("先用备用 API key（按用量付费）到重置；API 不行再自动换到 " + other_txt) if (has_key and other_txt) else \
          ("先用备用 API key（按用量付费）到重置" if has_key else None)
    move = f"直接换到 {other_txt}，重置后换回 {app}" if other_txt else None
    opts = [o for o in (api, move, wait) if o]
    if len(opts) < 2:
        return None
    # The pick depends on how long until the reset.
    if hours is not None and hours <= WAIT_IF_WITHIN_H:
        pick = wait
    elif api and (hours is None or hours <= API_UP_TO_H):
        pick = api
    else:
        pick = move or api or wait
    opts = [pick] + [o for o in opts if o != pick]
    opts[0] = opts[0] + "（推荐）"
    names = "、".join(who)
    text = (f"@{owner} {app} 这一档额度用到 {pct:.0f}% 了，{when} 重置（{left}）。在用它的：{names}。"
            f"到 100% 以后怎么办？选一个，到时候自动照做。")
    return text, opts


def classify(choice: str) -> str:
    c = choice or ""
    if c.startswith("先用备用 API"):
        return "api"
    if c.startswith("直接换到"):
        return "move"
    if c.startswith("等重置"):
        return "wait"
    return "other"
