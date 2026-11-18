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
