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


def test_the_visual_designers_card_reaches_her_directly(monkeypatch):
    import app
    monkeypatch.setattr(app, "config", {"team": {"mentions_from": "pm", "asks_owner": ["visual"]},
                                        "agents": {"pm": {}, "dev": {}, "visual": {}}})
    monkeypatch.setattr(app, "room_settings", {**app.room_settings, "username": "Lu"})
    card = {"id": 1, "sender": "visual", "type": "decision", "text": "@Lu 首屏两版选哪个", "attachments": [{"url": "/u/a.png"}],
            "metadata": {"choices": ["A（推荐）", "B"]}}
    assert app._lu_ask_for_pm("visual", card["text"], "p", card) is False         # hers to answer, the PM is not woken
    plain = {"id": 2, "sender": "visual", "type": "chat", "text": "@Lu 我先做 A 了", "attachments": []}
    assert app._lu_ask_for_pm("visual", plain["text"], "p", plain) is True        # no options: not hers
    same = {**card, "sender": "dev"}
    assert app._lu_ask_for_pm("dev", same["text"], "p", same) is True             # only who she named


def test_one_row_at_a_time_for_the_visual_designer(tmp_path, monkeypatch):
    import app, mcp_bridge, scranton_board as B
    b = B.Board(tmp_path / "board.json")
    monkeypatch.setattr(mcp_bridge, "BOARD", b)
    monkeypatch.setattr(app, "config", {"team": {"one_at_a_time": ["visual"]}, "agents": {"visual": {}, "dev": {}}})
    r1 = b.upsert("p", "pm", ask="BMW 首屏", who="visual", state="doing")
    r2 = b.upsert("q", "pm", ask="Concept 卡片", who="visual", state="todo")
    assert "already doing row" in mcp_bridge._one_at_a_time("q", r2["id"], "doing", "")       # second one waits
    assert mcp_bridge._one_at_a_time("p", r1["id"], "doing", "visual") == ""                   # the same row may be updated
    assert mcp_bridge._one_at_a_time("q", 0, "doing", "dev") == ""                              # only who she named
    b.upsert("p", "pm", id=r1["id"], state="later", note="等 Lu 选参考")
    assert mcp_bridge._one_at_a_time("q", r2["id"], "doing", "") == ""


def test_pm_does_not_retell_what_she_told_a_teammate_herself(monkeypatch):
    import time, app

    class S:
        def get_by_id(self, i):
            return {20387: {"id": 20387, "sender": "Lu", "timestamp": time.time(), "text": "@visual @pm 我想让你用图一的感觉，重新渲染一下图二"},
                    20300: {"id": 20300, "sender": "Lu", "timestamp": time.time(), "text": "@pm deck 第三页看不到"}}.get(i)
    monkeypatch.setattr(app, "store", S())
    monkeypatch.setattr(app, "config", {"team": {"mentions_from": "pm"}, "agents": {"pm": {}, "visual": {}, "dev": {}}})
    monkeypatch.setattr(app, "room_settings", {**app.room_settings, "username": "Lu"})
    long = "@visual Lu #20387：按图一的感觉重渲图二男人和背景的融合，先出一张静态视觉稿（两张图都先打开看）。只改人物与背景交界，屏幕/UI/双手不动。出稿 @pm，我转 Lu"
    assert "told @visual this herself" in app.sc_retold("pm", long)
    assert app.sc_retold("pm", "@visual #20387 先做这个，22:40 前") == ""          # order and time only
    assert app.sc_retold("pm", "@dev Lu #20300：第三页翻到才加载导致空白，改回一次加载全部，交改前改后图给我，我转 Lu，22:20 前") == ""   # she told the PM, not dev
    assert app.sc_retold("visual", long) == ""


def test_a_promised_time_on_the_board_is_a_real_time(tmp_path):
    import time, scranton_board as B
    b = B.Board(tmp_path / "board.json")
    at = time.mktime((2026, 11, 20, 0, 51, 0, 0, 0, -1))
    r = b.upsert("p", "pm", ask="Team setup 重排", who="dev", due="03:00", now=at)
    assert time.strftime("%m-%d %H:%M", time.localtime(B.due_ts(r))) == "11-20 03:00"
    late = b.upsert("p", "pm", ask="明天的事", who="dev", due="交 10:00", now=time.mktime((2026, 11, 20, 14, 0, 0, 0, 0, -1)))
    assert time.strftime("%m-%d %H:%M", time.localtime(B.due_ts(late))) == "11-21 10:00"     # 10:00 already gone: tomorrow's
    assert B.due_ts(b.upsert("p", "pm", ask="没有钟点", who="dev", due="今晚")) == 0
    again = b.upsert("p", "pm", id=r["id"], note="在做", now=at + 7200)                          # touching the row keeps the promise
    assert B.due_ts(again) == B.due_ts(r)


def test_a_restarted_teammate_is_handed_its_row_back(tmp_path, monkeypatch):
    import app, mcp_bridge, scranton_board as B
    b = B.Board(tmp_path / "board.json")
    monkeypatch.setattr(mcp_bridge, "BOARD", b)
    monkeypatch.setattr(app, "_quiet_channel", lambda ch: ch == "paused")
    b.upsert("p", "pm", ask="响应式：所有页铺满", who="dev", state="doing", due="18:00")
    b.upsert("p", "pm", ask="Trading menu 重排", who="dev", state="todo", due="09:00")
    b.upsert("paused", "pm", ask="别的项目", who="dev", state="doing")
    ch, text, _ = app._sc_resume_text("dev")
    assert ch == "p" and "接着做行 1「响应式：所有页铺满」" in text and "行 2" in text and "别的项目" not in text
    assert app._sc_resume_text("copy") is None            # holds nothing: not woken


def test_only_the_row_a_delivery_opens_with_and_not_an_acknowledgement():
    import app
    assert app._ACK_RE.match("行 146 收到：Marco 视频往右移，让男人整个露出来。")
    assert app._ACK_RE.match("收到，接着做")
    assert not app._ACK_RE.match("行 146（#21442）：Marco 的视频往右移了，男人整个在画面里")
    body = "行 146（#21442）：Marco 的视频往右移了。另外行 144 的边距没动。"
    import re
    assert app._row_ids(re.split(r"[：:。\n]", body, maxsplit=1)[0][:40]) == {146}


def test_two_things_in_one_message_to_her_get_a_hint(monkeypatch):
    import mcp_bridge
    monkeypatch.setattr(mcp_bridge, "_owner_name", lambda: "Lu")
    two = "@Lu #20625–#20628：\n1. 静态图：第 14 页换成你批过的那张，可以吗？\n2. 叹气：这次先不重生成，还是现在重做？"
    assert "one reply box" in mcp_bridge._two_asks_hint(two)
    assert mcp_bridge._two_asks_hint("@Lu 行 146：Marco 的视频往右移了，图左改前右改后。") == ""
    assert mcp_bridge._two_asks_hint("@dev 1. 先修边距？ 2. 再修翻页？") == ""       # not to her
