import mcp_bridge, scranton_board


class _Store:
    def __init__(self, msgs): self.m = {m["id"]: m for m in msgs}
    def get_by_id(self, i): return self.m.get(i)


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_bridge, "store", _Store([
        {"id": 1, "sender": "Lu", "text": "把首页改一下", "type": "chat"},
        {"id": 2, "sender": "pm", "text": "@Lu 首页用 A 还是 B？", "type": "chat"},
        {"id": 3, "sender": "pm", "text": "@dev 08:00 问 Lu", "type": "chat"},
    ]))
    monkeypatch.setattr(mcp_bridge, "_owner_name", lambda: "Lu")
    b = scranton_board.Board(tmp_path / "board.json")
    monkeypatch.setattr(mcp_bridge, "BOARD", b)
    return b


def test_waiting_for_lu_needs_a_question_she_can_see(tmp_path, monkeypatch):
    b = _setup(tmp_path, monkeypatch)
    assert mcp_bridge.asked_owner(2) and not mcp_bridge.asked_owner(1) and not mcp_bridge.asked_owner(3)
    assert not mcp_bridge.asked_owner(0) and not mcp_bridge.asked_owner(99)
    b.upsert("p", "pm", ask="首页", state="waiting_lu", msg=1)     # an old row: points at her own message
    b.upsert("p", "pm", ask="封面", state="waiting_lu", msg=2)
    view = {r["ask"]: r for r in mcp_bridge.board_view("p")}
    assert view["首页"]["state"] == "doing" and view["首页"]["not_asked"]
    assert view["封面"]["state"] == "waiting_lu"
    assert [r["state"] for r in b.rows("p")] == ["waiting_lu", "waiting_lu"]   # stored rows untouched


def test_parked_rows_are_not_stuck_and_her_own_rows_are_hers(tmp_path, monkeypatch):
    b = _setup(tmp_path, monkeypatch)
    b.upsert("p", "pm", ask="Contour", state="blocked", who="dev", note="11-17 14:00 复核：Contour 暂停（Lu #14726）")
    b.upsert("p", "pm", ask="动效复验", state="blocked", who="motion", note="Lu 无需操作；待行16定稿后做")
    b.upsert("p", "pm", ask="视频压缩", state="blocked", who="video", note="ffmpeg 没装，需要 ops 装")
    b.upsert("p", "pm", ask="Concept 模型", state="doing", who="Lu", note="Lu 自己用 ChatGPT 出模型")
    view = {r["ask"]: r for r in mcp_bridge.board_view("p")}
    assert view["Contour"]["state"] == "later" and view["动效复验"]["state"] == "later"
    assert view["视频压缩"]["state"] == "blocked" and view["Concept 模型"].get("yours")
    # a parked row is nobody's load and is not re-checked every four hours
    import time
    rep = scranton_board.housekeeping(b, lambda u: None, now=time.time() + 6 * 3600)
    assert sorted(r["ask"] for r in rep["p"]["stale"]) == ["Concept 模型", "视频压缩"]
    assert "later" in scranton_board.STATES and scranton_board.STATE_ZH["later"] == "以后做"
