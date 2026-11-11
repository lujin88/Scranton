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
