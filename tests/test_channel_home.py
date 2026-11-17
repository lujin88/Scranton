"""Lu, 11-17: an answer goes where she asked; a reply goes with the message it answers."""
import time
import types

import mcp_bridge as B


class _Store:
    def __init__(self):
        import threading
        self._lock = threading.Lock(); self._messages = []

    def add(self, sender, text, channel="general", ago=0, **kw):
        m = {"id": len(self._messages) + 1, "sender": sender, "text": text, "channel": channel,
             "type": "chat", "timestamp": time.time() - ago}
        self._messages.append(m); return m

    def get_by_id(self, i):
        return next((m for m in self._messages if m["id"] == i), None)


def _setup(monkeypatch):
    s = _Store()
    monkeypatch.setattr(B, "store", s)
    monkeypatch.setattr(B, "_owner_name", lambda: "Lu")
    return s


def test_answer_to_lu_in_another_channel_is_held(monkeypatch):
    s = _setup(monkeypatch)
    s.add("Lu", "@pm 第 3 页标题太大", "client-advisory-slid", ago=60)
    assert B._owner_waiting("pm", "lu-portfolio", "@Lu 收到，改好了")[0] == "client-advisory-slid"
    assert B._owner_waiting("pm", "client-advisory-slid", "@Lu 收到，改好了") is None       # right place


def test_dm_question_is_answered_in_the_dm(monkeypatch):
    s = _setup(monkeypatch)
    s.add("Lu", "MAN 那页怎么样了", "dm-pm", ago=30)                 # no @ needed in a DM
    assert B._owner_waiting("pm", "man-screen", "@Lu MAN 那页做完了")[0] == "dm-pm"


def test_talking_to_teammates_elsewhere_is_never_held(monkeypatch):
    s = _setup(monkeypatch)
    s.add("Lu", "把 MAN 首屏改一下", "dm-pm", ago=30)
    assert B._owner_waiting("pm", "man-screen", "@dev Lu 在 #dm-pm（#1）说：「把 MAN 首屏改一下」") is None


def test_once_answered_there_other_channels_are_free(monkeypatch):
    s = _setup(monkeypatch)
    s.add("Lu", "@pm 第 3 页标题太大", "client-advisory-slid", ago=120)
    s.add("pm", "@Lu 收到", "client-advisory-slid", ago=60)
    assert B._owner_waiting("pm", "lu-portfolio", "@Lu 首页时间线的图") is None


def test_old_questions_and_other_teammates_dont_count(monkeypatch):
    s = _setup(monkeypatch)
    s.add("Lu", "@pm 这个改一下", "contour-slide", ago=B.OWED_FOR + 60)
    s.add("Lu", "@dev 看一下", "eon-slide", ago=30)
    assert B._owner_waiting("pm", "lu-portfolio", "@Lu 图来了") is None


def test_her_card_clicks_and_ok_are_not_questions(monkeypatch):
    s = _setup(monkeypatch)
    s.add("Lu", "@pm A：按四段换背景 (推荐)", "client-advisory-slid", ago=40)
    s.add("Lu", "@pm 好", "client-advisory-slid", ago=20)
    assert B._owner_waiting("pm", "man-screen", "@Lu MAN 首屏的图") is None
