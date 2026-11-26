"""探索 work starts with the goal in the teammate's own words (Lu, 11-26)."""
import time

import mcp_bridge as B


class _Store:
    def __init__(self, msgs): self.msgs = msgs
    def get_recent(self, count=50, channel=None): return [m for m in self.msgs if m.get("channel") == channel][-count:]
    def get_by_id(self, i): return next((m for m in self.msgs if m.get("id") == i), None)


def _setup(monkeypatch, msgs):
    monkeypatch.setattr(B, "config", {"team": {"lead": "pm"}})
    monkeypatch.setattr(B, "store", _Store(list(msgs)))
    monkeypatch.setattr(B, "_owner_name", lambda: "Lu")


def _m(id, sender, text, ago_min, ch="lu-portfolio"):
    return {"id": id, "sender": sender, "text": text, "channel": ch, "timestamp": time.time() - ago_min * 60}


TASK = _m(10, "pm", "@visintern 探索｜行 88：LinkedIn feature 图，出 2 版", 30)


def test_first_message_after_exploration_work_must_restate_the_goal(monkeypatch):
    _setup(monkeypatch, [TASK])
    err = B._restate_first("visintern", "@visualqa 两版在这里，请验", "lu-portfolio")
    assert err.startswith("Not sent.") and "#10" in err and "@pm" in err and "目标：" in err and "Do not @Lu" in err
    ok = "@pm 目标：让招聘方一眼看懂 Lu 用一支 AI 团队走完整个流程\n要解决的问题：现在的图只是工具截图，看不出流程"
    assert B._restate_first("visintern", ok, "lu-portfolio") == ""


def test_once_said_later_messages_go_through(monkeypatch):
    _setup(monkeypatch, [TASK, _m(11, "visintern", "@pm 目标：让招聘方看懂流程\n要解决的问题：现在看不出", 20)])
    assert B._restate_first("visintern", "@visualqa 两版在这里，请验", "lu-portfolio") == ""


def test_only_exploration_work_and_only_the_one_it_was_given_to(monkeypatch):
    _setup(monkeypatch, [_m(10, "pm", "@dev 照做｜行 5：把按钮改成 40px", 30), TASK])
    assert B._restate_first("dev", "@qa PR #9 请验", "lu-portfolio") == ""            # 照做: nothing to restate
    assert B._restate_first("visual", "@Lu 两个方向", "lu-portfolio") == ""           # not the one asked
    assert B._restate_first("pm", "@visintern 16:00 前交", "lu-portfolio") == ""       # the project manager
    assert B._restate_first("visintern", "别的项目的话", "eon-slide") == ""           # another channel


def test_when_lu_gave_the_work_the_lines_go_to_the_pm_not_to_her(monkeypatch):
    _setup(monkeypatch, [_m(10, "Lu", "@visual 探索｜首页换一个更安静的方向", 10)])
    err = B._restate_first("visual", "@Lu 我先问一下", "lu-portfolio")
    assert "send @pm two lines" in err and "Do not @Lu" in err


def test_old_work_is_not_chased(monkeypatch):
    _setup(monkeypatch, [_m(10, "pm", "@visintern 探索｜行 88", 7 * 60)])
    assert B._restate_first("visintern", "@visualqa 请验", "lu-portfolio") == ""
