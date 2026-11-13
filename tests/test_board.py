import time
import pytest
import scranton_board as b


def test_board_rows(tmp_path):
    B = b.Board(tmp_path / "board.json")
    r = B.upsert("c", "pm", ask="BMW 首屏换新设计", who="webdev", due="14:00")
    assert r["id"] == 1 and r["state"] == "todo"
    B.upsert("c", "pm", id=1, state="in_pr", link="https://x/pull/1")
    B.upsert("c", "pm", ask="菜单改名", state="waiting_lu")
    rows = b.Board(tmp_path / "board.json").rows("c")
    assert [x["state"] for x in rows] == ["in_pr", "waiting_lu"]
    assert b.summary(rows) == "2 open · 1 在 PR · 1 等你"
    with pytest.raises(ValueError):
        B.upsert("c", "pm", ask="x", state="merged")
    with pytest.raises(ValueError):
        B.upsert("c", "pm", state="doing")   # a new row needs ask
    assert B.remove("c", 2) and not B.remove("c", 2)


def test_live_rows_drop_after_a_day(tmp_path):
    B = b.Board(tmp_path / "board.json")
    B.upsert("c", "pm", ask="done thing", state="live", now=time.time() - 25 * 3600)
    B.upsert("c", "pm", ask="open thing")
    assert [x["ask"] for x in B.rows("c")] == ["open thing"]


def test_chat_board_tool(tmp_path, monkeypatch):
    import mcp_bridge
    monkeypatch.setattr(mcp_bridge, "BOARD", b.Board(tmp_path / "board.json"))
    monkeypatch.setattr(mcp_bridge, "_resolve_tool_identity", lambda s, ctx, **k: (s, None))
    out = mcp_bridge.chat_board("pm", "set", channel="lu-portfolio", ask="How I Work 加卡片", who="dev")
    assert '"ok": true' in out
    assert "How I Work" in mcp_bridge.chat_board("pm", "read", channel="lu-portfolio")
    assert mcp_bridge.chat_board("pm", "set", channel="lu-portfolio", id=1, state="nope").startswith("Error")


def test_row_keeps_message_id(tmp_path):
    B = b.Board(tmp_path / "board.json")
    B.upsert("c", "pm", ask="视频两版选一个", state="waiting_lu", msg=7820)
    assert B.rows("c")[0]["msg"] == 7820
    B.upsert("c", "pm", id=1, note="等你选")
    assert B.rows("c")[0]["msg"] == 7820


def test_housekeeping_merged_stale_overloaded(tmp_path):
    B = b.Board(tmp_path / "board.json")
    old = time.time() - 6 * 3600
    B.upsert("c", "pm", ask="BMW 首屏", state="in_pr", who="webdev", link="https://github.com/x/y/pull/1", now=old)
    for i in range(6):
        B.upsert("c", "pm", ask=f"活 {i}", state="doing", who="webdev", now=old)
    B.upsert("c", "pm", ask="新的", state="doing", who="dev")
    rep = b.housekeeping(B, lambda u: "MERGED" if u.endswith("/1") else "OPEN")["c"]
    assert [r["ask"] for r in rep["merged"]] == ["BMW 首屏"]
    assert B.rows("c")[0]["state"] == "live"
    assert len(rep["stale"]) == 6 and rep["overloaded"] == {"webdev": 6}
    txt = b.nudge_text(rep)
    assert "6 行超过 4 小时" in txt and "webdev 6 件" in txt
    # reported once per window
    assert b.housekeeping(B, lambda u: "OPEN") == {}


def test_long_message_note():
    import mcp_bridge
    assert mcp_bridge._length_note("短", []) == ""
    assert "characters" in mcp_bridge._length_note("x" * 500, [])
    assert mcp_bridge._length_note("x" * 500, ["A"]) == ""
    assert mcp_bridge._length_note("问你：\nA. 一\nB. 二\n" + "x" * 500, []) == ""


def test_idle_poke(tmp_path, monkeypatch):
    import app, mcp_bridge
    B = b.Board(tmp_path / "board.json")
    B.upsert("c", "pm", ask="4 只站立定帧", state="doing", who="visintern")
    B.upsert("c", "pm", ask="别的", state="doing", who="motion")
    now = time.time()
    monkeypatch.setattr(app, "config", {"agents": {"visintern": {}, "motion": {}}})
    monkeypatch.setattr(mcp_bridge, "_presence", {"visintern": now, "motion": now})
    monkeypatch.setattr(mcp_bridge, "_activity", {"visintern": False, "motion": True})
    monkeypatch.setattr(app, "_sc_idle_since", {"visintern": now - 20 * 60})
    pokes = app._sc_idle_pokes(B, now)
    assert [(p[1]) for p in pokes] == ["visintern"] and "停了 20 分钟" in pokes[0][3]
    assert app._sc_idle_pokes(B, now + 60) == []          # once per 30 min
    mcp_bridge._presence["visintern"] = now + 1890
    assert len(app._sc_idle_pokes(B, now + 1900)) == 1
    mcp_bridge._presence["visintern"] = now + 3790
    assert app._sc_idle_pokes(B, now + 3800) == []        # at most twice until the row changes
