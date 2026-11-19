"""Lu, 11-18: what she said is kept by Scranton, taken by citing its number, findable by page."""
import time

import scranton_said as S


def _m(i, text, ch="slides", ago=0, atts=None, sender="Lu"):
    return {"id": i, "text": text, "channel": ch, "timestamp": time.time() - ago, "sender": sender,
            "type": "chat", "attachments": atts or []}


def _s(tmp_path):
    return S.Said(tmp_path / "said.json")


def test_keeps_instructions_not_clicks_or_ok(tmp_path):
    s = _s(tmp_path)
    assert s.add(_m(1, "@pm 时长页的背景不要条纹，照原稿左浅右深"))
    assert not s.add(_m(2, "@pm A：按四段换背景 (推荐)"))
    assert not s.add(_m(3, "@pm 好的"))
    assert not s.add(_m(1, "@pm 时长页的背景不要条纹，照原稿左浅右深"))      # once
    assert [it["id"] for it in s.open_items()] == [1]


def test_citing_the_number_takes_it(tmp_path):
    s = _s(tmp_path)
    s.add(_m(15247, "@pm 第 7 页加四个短标签，贴在照片旁边"))
    assert S.cited_ids("@dev Lu #15247：第 7 页加四个短标签。交 19:00") == [15247]
    assert s.take([15247, 999], "pm", ref=15250) == [15247]
    assert s.open_items() == []
    assert s.take([15247], "dev") == []                                   # already taken


def test_find_gives_everything_about_a_page_latest_last(tmp_path):
    s = _s(tmp_path)
    s.add(_m(1, "@pm 时长页照原稿：整屏左右两半", ago=7200, atts=[{"url": "/uploads/ref.png"}]))
    s.add(_m(2, "@pm 封面 UBS 要红色", ago=3600))
    s.add(_m(3, "@pm 这页右下那行小字删掉", ago=60), context="pm: 时长页改好了，见附图")   # "这页": found through what she replied to
    got = s.find("slides", "时长页")
    assert [g["id"] for g in got] == [1, 3] and got[0]["atts"] == ["/uploads/ref.png"]
    assert s.find("other", "时长页") == []


def test_note_lists_what_nobody_took_and_not_too_often(tmp_path):
    s = _s(tmp_path)
    s.add(_m(1, "@pm 第 3 页条纹改成从左边斜着进来", ago=20 * 60))
    s.add(_m(2, "@pm 刚说的这条还不到十五分钟", ago=60))
    items = s.due_note("slides")
    assert [it["id"] for it in items] == [1]
    text = S.note_text("Lu", items)
    assert text.startswith("@pm ") and "#1 " in text and "@Lu" not in text
    assert s.due_note("slides") == []                                     # told: not again for 45 min


def test_skip_needs_no_take_and_shows_in_counts(tmp_path):
    s = _s(tmp_path)
    s.add(_m(1, "@pm 把这个也推到新 repo 里去"))
    assert s.skip([1], "pm", "法务不让放 UBS 截图") == [1]
    assert s.counts("slides") == {"open": 0, "today": 1, "skipped": 1}


def test_backfill_is_findable_but_never_chased(tmp_path):
    s = _s(tmp_path)
    old = [_m(5, "@pm 信件要描边，亮起来之后不要那么亮", ago=86400), _m(6, "@Lu 收到", sender="pm", ago=86000)]
    assert s.backfill(old, "Lu") == 1
    assert s.open_items() == [] and s.find("slides", "描边")[0]["state"] == "old"


def test_questions_are_settled_by_an_answer_changes_are_not():
    assert S.is_question("@pm 为什么实习生又 stop 了？")
    assert S.is_question("@pm 即梦连上了吗？")
    assert not S.is_question("@pm 这页底下不是讲了四遍了吗？为什么还是没有改这个 wireframe？")   # asks for a change
    assert not S.is_question("@pm 把第二页的卡片放过来")


def test_an_assignment_that_cites_her_message_carries_her_words_and_pictures(tmp_path, monkeypatch):
    import mcp_bridge as B
    s = _s(tmp_path)
    s.add(_m(17410, "@pm 卡片第一页和第二页要一样高，红色圈出来的还是 wireframe 的位置", atts=[{"url": "/uploads/red-box.png"}]))
    monkeypatch.setattr(B, "SAID", s)
    monkeypatch.setattr(B, "_owner_name", lambda: "Lu")
    got = B._owner_words_for({"sender": "pm", "text": "@webdev 急件（Lu #17410）：第 1 步背景网格用第 2 步那一套。交 10:35"})
    assert got[0]["id"] == 17410 and "一样高" in got[0]["said"]
    assert got[0]["pictures"] and got[0]["pictures"][0].endswith("red-box.png")
    assert B._owner_words_for({"sender": "Lu", "text": "@pm 见 #17410"}) == []          # her own messages: nothing to add
    assert B._owner_words_for({"sender": "pm", "text": "@webdev 没有编号的派活"}) == []


def test_a_result_waits_for_her_verdict(tmp_path):
    import scranton_said as S
    said = S.Said(tmp_path / "said.json")
    said.add({"id": 10, "sender": "Lu", "text": "@pm 首页的气球放大一点，别被裁掉", "channel": "p", "timestamp": 1795000000})
    said.add({"id": 11, "sender": "Lu", "text": "@pm 好的", "channel": "p", "timestamp": 1795000001})
    assert said.mark_done([10, 11, 99], 20, "visual", now=1795000100) == [10]       # "好的" is not an instruction
    assert [c["id"] for c in said.to_check(now=1795000200)] == [10] and said.get(10)["state"] == "taken"
    back = said.verdict(10, False, "还是被裁了")
    assert back["rounds"] == 1 and back["last_no"] == {"msg": 20, "by": "visual", "note": "还是被裁了"} and said.to_check(now=1795000300) == []
    assert said.mark_done([10], 21, "visual", now=1795000400) == [10]               # shown again
    assert said.accept_result(21) == [10] and said.get(10)["verdict"] == "ok" and said.to_check(now=1795000500) == []
    assert said.mark_done([10], 22, "visual") == []                                  # finished stays finished
    assert said.verdict(11, True) is None


def test_first_time_rate_and_pending(tmp_path):
    import scranton_said as S
    said = S.Said(tmp_path / "said.json")
    import time as _t
    now = _t.time()
    for i in (1, 2, 3):
        said.add({"id": i, "sender": "Lu", "text": f"@pm 第 {i} 页的标题往左移一点对齐", "channel": "p", "timestamp": now})
    said.take([1, 2, 3], "pm", 9)
    assert [it["id"] for it in said.pending_for("p")] == [1, 2, 3]
    said.mark_done([1, 2], 20, "visual")
    assert [it["id"] for it in said.pending_for("p")] == [3]
    said.verdict(1, True); said.verdict(2, False, "没对齐")
    said.mark_done([2], 21, "visual"); said.verdict(2, True)
    r = said.first_time(7)
    assert (r["judged"], r["first"]) == (2, 1) and r["by"] == [{"who": "visual", "judged": 2, "first": 1}]


def test_board_row_keeps_checks(tmp_path):
    import scranton_board as B
    b = B.Board(tmp_path / "board.json")
    row = b.upsert("p", "pm", ask="首页气球", who="visual", check="390 宽不横向滚动\n· 气球不被裁；标题同字号")
    assert row["check"] == ["390 宽不横向滚动", "气球不被裁", "标题同字号"]
    assert b.upsert("p", "pm", id=row["id"], state="doing")["check"] == row["check"]
