"""Lu, 11-18: finished work reaches her from whoever did it; the board follows what happens."""
import app
import mcp_bridge
import scranton_board


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "config", {"team": {"mentions_from": "pm"}, "agents": {"pm": {}, "dev": {}, "visualqa": {}}})
    monkeypatch.setitem(app.room_settings, "username", "Lu")
    b = scranton_board.Board(tmp_path / "board.json")
    monkeypatch.setattr(mcp_bridge, "BOARD", b)
    return b


PIC = [{"name": "p7.png", "url": "/uploads/p7.png"}]


def test_a_delivery_with_a_picture_is_not_passed_to_the_pm(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    done = {"id": 5, "sender": "dev", "type": "chat", "text": "@Lu 第 7 页四个标签加好了（Lu #17410，行 3），改前｜改后见图。", "attachments": PIC}
    assert app._is_delivery(done)
    assert app._lu_ask_for_pm("dev", done["text"], "slides", done) is False      # hers directly, the PM isn't woken
    ask = {"id": 6, "sender": "dev", "type": "chat", "text": "@Lu 这页标题要不要再小一点？", "attachments": PIC}
    assert not app._is_delivery(ask)
    assert app._lu_ask_for_pm("dev", ask["text"], "slides", ask) is True          # a question still goes to the PM
    bare = {"id": 7, "sender": "dev", "type": "chat", "text": "@Lu 改好了。", "attachments": []}
    assert app._lu_ask_for_pm("dev", bare["text"], "slides", bare) is True        # nothing to look at: not a delivery


def test_board_follows_the_delivery_and_her_answer(monkeypatch, tmp_path):
    b = _setup(monkeypatch, tmp_path)
    row = b.upsert("slides", "pm", ask="第 7 页加四个短标签", state="doing", who="dev")
    done = {"id": 50, "sender": "dev", "type": "chat", "text": f"@Lu 第 7 页标签加好了，行 {row['id']}，见图。", "attachments": PIC}
    app._sc_board_follow(done, "dev", done["text"], "slides", "chat", False)
    r = b.rows("slides")[0]
    assert r["state"] == "waiting_lu" and r["msg"] == 50
    reply = {"id": 51, "sender": "Lu", "type": "chat", "text": "标签再小一号", "reply_to": 50}
    app._sc_board_follow(reply, "Lu", reply["text"], "slides", "chat", True)
    r = b.rows("slides")[0]
    assert r["state"] == "doing" and "Lu 回了（#51）" in r["note"] and "再小一号" in r["note"]


def test_her_answer_to_a_question_named_in_the_note_also_counts(monkeypatch, tmp_path):
    b = _setup(monkeypatch, tmp_path)
    b.upsert("portfolio", "pm", ask="Gratula 视觉稿", state="waiting_lu", who="research", note="等 Lu 挑参考（#18329）")
    b.upsert("portfolio", "pm", ask="别的事", state="waiting_lu", who="dev", note="等 Lu 选 #99")
    reply = {"id": 18400, "sender": "Lu", "type": "chat", "text": "@pm B：Duolingo", "reply_to": 18329}
    app._sc_board_follow(reply, "Lu", reply["text"], "portfolio", "chat", True)
    states = {r["ask"]: r["state"] for r in b.rows("portfolio")}
    assert states == {"Gratula 视觉稿": "doing", "别的事": "waiting_lu"}


def test_her_thumbs_up_closes_the_row_that_was_waiting_for_her(monkeypatch, tmp_path):
    b = _setup(monkeypatch, tmp_path)
    b.upsert("slides", "pm", ask="文案 review", state="waiting_lu", who="webdev", msg=18346, note="改前|改后图已发 Lu")
    b.upsert("slides", "pm", ask="Hub 布局", state="waiting_lu", who="dev", note="等她选 #18334")
    assert app._sc_board_seen({"channel": "slides"}, 18346, "👍") == 1
    rows = {r["ask"]: r for r in b.rows("slides")}
    assert rows["文案 review"]["state"] == "live" and "看过了" in rows["文案 review"]["note"]
    assert rows["Hub 布局"]["state"] == "waiting_lu"          # a different message: still hers to answer


def test_a_row_she_was_doing_herself_leaves_her_list_once_she_answers_it(monkeypatch, tmp_path):
    """11-19: row 69 (who = Lu) came back as "yours" right after she wrote 行 69：这个可以删掉了."""
    b = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_bridge, "_owner_name", lambda: "Lu")
    monkeypatch.setattr(mcp_bridge, "store", None)
    row = b.upsert("p", "pm", ask="Concept 组新布局", state="doing", who="Lu", note="Lu 自己用 ChatGPT 出模型")
    assert mcp_bridge.board_view("p")[0].get("yours")
    said = {"id": 90, "sender": "Lu", "type": "chat", "text": f"@pm 行 {row['id']}：这个你可以删掉了，我们的 research 已经做完了"}
    app._sc_board_follow(said, "Lu", said["text"], "p", "chat", True)
    after = mcp_bridge.board_view("p")[0]
    assert after["state"] == "doing" and after["who"] == "pm" and not after.get("yours")
    assert after["note"].startswith("Lu 回了（#90）")


def test_one_answer_can_name_several_rows(monkeypatch, tmp_path):
    b = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_bridge, "store", None)
    for ask in ("手机版菜单", "ETF 页开头", "四季"):
        b.upsert("p", "pm", ask=ask, state="waiting_lu", who="pm", msg=50)
    assert app._row_ids("@pm 行 1、2 和 3：都用 A") == {1, 2, 3} and app._row_ids("行 12") == {12}
    said = {"id": 91, "sender": "Lu", "type": "chat", "text": "@pm 行 1、2、3：第一题 A，第二题 B，四季就按现在的"}
    app._sc_board_follow(said, "Lu", said["text"], "p", "chat", True)
    assert [r["state"] for r in b.rows("p")] == ["doing", "doing", "doing"]
