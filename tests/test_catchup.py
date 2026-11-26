"""接回: since her last message here, what happened and what waits for her (Lu, 11-26)."""
import time
import scranton_catchup as cu

NOW = 1_800_000_000.0


def _m(id, sender, ago_min, text="x", **meta):
    m = {"id": id, "sender": sender, "text": text, "timestamp": NOW - ago_min * 60, "type": "chat"}
    if meta:
        m["metadata"] = meta
    return m


def test_anchor_is_her_last_message_before_this_visit():
    msgs = [_m(1, "Lu", 600), _m(2, "pm", 500), _m(3, "Lu", 300), _m(4, "dev", 200),
            _m(5, "Lu", 3, "我回来了"),                       # just now: this visit, not "last time"
            _m(6, "Lu", 100, "（Claude 代 Lu 发）…", via="claude"),   # sent for her: she didn't type it
            _m(7, "Lu", 90, "/接回")]
    assert cu.anchor(msgs, "Lu", NOW)["id"] == 3


def test_gather_counts_what_came_after_and_what_waits():
    msgs = [_m(1, "Lu", 300), _m(2, "pm", 200), _m(3, "dev", 100), _m(4, "system", 50), _m(5, "Lu", 2)]
    rows = [{"id": 1, "ask": "旧的等她", "state": "waiting_lu", "at": NOW - 9000 * 60, "who": "pm"},
            {"id": 2, "ask": "刚上线", "state": "live", "at": NOW - 60 * 60},
            {"id": 3, "ask": "在做", "state": "doing", "at": NOW - 30 * 60, "who": "dev"},
            {"id": 4, "ask": "以后", "state": "later", "at": NOW - 30 * 60},
            {"id": 5, "ask": "早就上线", "state": "live", "at": NOW - 400 * 60}]
    info = cu.gather(msgs, rows, "Lu", NOW)
    assert info["messages"] == 2
    assert [r["id"] for r in info["done"]] == [2]
    assert [r["id"] for r in info["moving"]] == [3]
    assert [r["id"] for r in info["for_her"]] == [1]            # waits for her however old it is
    text = cu.request_text("pm", info)
    assert text.startswith("@pm 接回｜") and "行 1「旧的等她」" in text and "行 2「刚上线」" in text
    assert "最多 5 项" in text and "只写卡片在哪条消息" in text


def test_nothing_new_costs_no_model_call():
    info = cu.gather([_m(1, "Lu", 300), _m(2, "Lu", 1)], [], "Lu", NOW)
    assert cu.nothing(info) and "没有新消息" in cu.quiet_text(info)


def test_never_spoke_here_looks_at_the_last_day():
    info = cu.gather([_m(1, "pm", 60), _m(2, "pm", 3000)], [], "Lu", NOW)
    assert info["anchor"] is None and info["messages"] == 1
    assert "最近没在这里说过话" in cu.when_text(info)


def test_endpoint_asks_the_pm_once(monkeypatch):
    import app, mcp_bridge
    posted = []
    class _Store:
        def get_recent(self, n, channel=None): return [_m(1, "Lu", 300), _m(2, "dev", 100)]
        def add(self, sender, text, **k): posted.append((sender, text, k))
    class _Board:
        def rows(self, ch): return [{"id": 9, "ask": "选字号", "state": "waiting_lu", "at": 1}]
    monkeypatch.setattr(app, "store", _Store())
    monkeypatch.setattr(mcp_bridge, "BOARD", _Board())
    monkeypatch.setattr(app, "room_settings", {"channels": ["general", "lu-portfolio", "dm-visual"], "username": "Lu"})
    monkeypatch.setattr(app, "config", {"agents": {"pm": {}, "visual": {}}})
    monkeypatch.setattr(app, "_CATCHUP_AT", {})
    monkeypatch.setattr(cu.time, "time", lambda: NOW)
    monkeypatch.setattr(app.time, "time", lambda: NOW)
    out = app._sc_catch_up("lu-portfolio")
    assert out["state"] == "asked" and out["to"] == "pm" and out["for_her"] == 1
    assert posted[0][0] == "Scranton" and posted[0][1].startswith("@pm 接回") and posted[0][2]["channel"] == "lu-portfolio"
    assert app._sc_catch_up("lu-portfolio")["state"] == "already asked" and len(posted) == 1
    assert app._sc_catch_up("dm-visual")["to"] == "visual"      # in a DM the teammate answers, not the PM
    assert app._sc_catch_up("nope")["ok"] is False
