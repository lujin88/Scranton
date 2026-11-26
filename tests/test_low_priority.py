"""Low-priority projects: Gemini teammates first, and only the project manager brings things to Lu."""
import time

import mcp_bridge as B


class _Store:
    def __init__(self, msgs):
        self.msgs = msgs

    def get_recent(self, count=50, channel=None):
        return [m for m in self.msgs if m.get("channel") == channel][-count:]

    def get_by_id(self, i):
        return next((m for m in self.msgs if m.get("id") == i), None)


CFG = {"team": {"lead": "pm", "low_priority": {"channels": ["lumin"], "first": {"dev": "gemdev", "visual": "visintern"}}}}


def _setup(monkeypatch, msgs=()):
    monkeypatch.setattr(B, "config", CFG)
    monkeypatch.setattr(B, "store", _Store(list(msgs)))
    monkeypatch.setattr(B, "_owner_name", lambda: "Lu")


def test_in_a_low_priority_project_a_teammate_is_sent_to_the_pm_instead_of_lu(monkeypatch):
    _setup(monkeypatch)
    err = B._low_lane_hold("gemdev", "@Lu 行 5 做完了，看一下", "lumin", None)
    assert err.startswith("Not sent.") and "@pm" in err and "once a day" in err
    assert B._low_lane_hold("pm", "@Lu 今天低优先级项目要你定的 2 件", "lumin", None) == ""       # the project manager may
    assert B._low_lane_hold("gemdev", "@qa 行 5 请验", "lumin", None) == ""                        # not addressed to her
    assert B._low_lane_hold("visual", "@Lu 行 88 两个方向", "lu-portfolio", None) == ""            # another project


def test_while_lu_is_in_the_channel_or_is_being_answered_it_goes_through(monkeypatch):
    now = time.time()
    _setup(monkeypatch, [{"id": 1, "sender": "Lu", "channel": "lumin", "timestamp": now - 20 * 60, "text": "这个怎么样了"}])
    assert B._low_lane_hold("gemdev", "@Lu 做完了", "lumin", None) == ""
    _setup(monkeypatch, [{"id": 2, "sender": "Lu", "channel": "lumin", "timestamp": now - 5 * 3600, "text": "行 5 改成完整度"}])
    assert B._low_lane_hold("gemdev", "@Lu 改好了", "lumin", 2) == ""                              # a reply to her message
    assert B._low_lane_hold("gemdev", "@Lu 改好了", "lumin", None).startswith("Not sent.")          # five hours later, not a reply


def test_the_pm_is_reminded_who_goes_first_but_not_stopped(monkeypatch):
    _setup(monkeypatch)
    hint = B._low_lane_hint("pm", "@dev 照做｜行 5 评分改成完整度，交 12:30", "lumin")
    assert "@gemdev before @dev" in hint
    assert B._low_lane_hint("pm", "@dev 照做｜行 5 第 2 次没过，转你", "lumin") == ""
    assert B._low_lane_hint("pm", "@gemdev 照做｜行 5 评分改成完整度", "lumin") == ""
    assert B._low_lane_hint("pm", "@dev 照做｜行 16 页面结构", "lu-portfolio") == ""
    assert B._low_lane_hint("qa", "@dev 照做｜行 5", "lumin") == ""
    assert B._low_lane_hint("pm", "@dev 行 5 进度怎么样", "lumin") == ""                           # not an assignment
