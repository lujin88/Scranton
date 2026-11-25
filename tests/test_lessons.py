import json
import time

import app
import mcp_bridge
import scranton_lessons as sl
import scranton_said


def test_proposed_then_kept_then_handed_to_readers(tmp_path, monkeypatch):
    L = sl.Lessons(tmp_path / "lessons.json")
    monkeypatch.setattr(mcp_bridge, "LESSONS", L)
    got = L.propose("deck", ["- 每页标题的位置和字号一致 #101", "2. 主视觉不用缩小的界面截图（#102）", "每页标题的位置和字号一致 #101", "x #101", "没有出处的一条"], by="harness")
    assert [g["text"] for g in got] == ["每页标题的位置和字号一致", "主视觉不用缩小的界面截图"]
    assert L.text_for("deck") == ""                        # nothing reaches the team before she keeps it
    assert L.decide("deck", got[0]["id"], True) and L.decide("deck", got[1]["id"], False)
    assert not L.decide("deck", 99, True)
    out = json.loads(mcp_bridge._serialize_messages([
        {"id": 1, "sender": "pm", "text": "a", "type": "chat", "time": "09:00", "channel": "deck"},
        {"id": 2, "sender": "pm", "text": "b", "type": "chat", "time": "09:01", "channel": "deck"},
        {"id": 3, "sender": "pm", "text": "c", "type": "chat", "time": "09:02", "channel": "other"}]))
    assert "project_lessons" not in out[0] and "每页标题的位置和字号一致" in out[1]["project_lessons"] and "project_lessons" not in out[2]
    assert "主视觉" not in out[1]["project_lessons"]
    assert sl.Lessons(tmp_path / "lessons.json").get("deck")["kept"][0]["text"] == "每页标题的位置和字号一致"   # survives a restart


def test_cap_and_her_own_and_remove(tmp_path):
    L = sl.Lessons(tmp_path / "l.json")
    for i in range(sl.MAX_KEPT + 3):
        assert L.add("p", f"偏好第 {i} 条的内容")          # her own lines need no source
    kept = L.get("p")["kept"]
    assert len(kept) == sl.MAX_KEPT and kept[0]["text"] == "偏好第 3 条的内容"      # the oldest three were pushed out
    assert L.remove("p", kept[0]["id"]) and len(L.get("p")["kept"]) == sl.MAX_KEPT - 1
    assert L.add("p", kept[1]["text"]) is None                                    # already there


def test_daily_request_only_when_she_corrected_enough(tmp_path, monkeypatch):
    L = sl.Lessons(tmp_path / "l.json")
    said = scranton_said.Said(tmp_path / "said.json")
    now = time.mktime((2026, 11, 19, 9, 0, 0, 0, 0, -1))
    for i, t in enumerate(["这个不是我要的，标题怎么又跳了", "字号太大了，我说过了", "跟参考完全不像，重新做", "好的，就这样"]):
        said.add({"id": 100 + i, "sender": "Lu", "text": "@pm " + t, "channel": "deck", "timestamp": now - 3600 * (i + 1)})
    said.add({"id": 200, "sender": "Lu", "text": "@pm 这个不对", "channel": "quiet", "timestamp": now - 3600})
    monkeypatch.setattr(mcp_bridge, "LESSONS", L)
    monkeypatch.setattr(app, "_sc_said", lambda: said)
    monkeypatch.setattr(app, "_project_channels", lambda: ["deck", "quiet", "dm-pm"])
    monkeypatch.setattr(app, "_paused_channels", lambda: set())
    monkeypatch.setattr(app, "config", {"agents": {"harness": {}, "pm": {}}, "team": {}})
    assert app._sc_lessons_tick(now - 4 * 3600) == []          # 05:00: not before 07:00
    got = app._sc_lessons_tick(now)
    assert [ch for ch, _ in got] == ["deck"] and got[0][1].startswith("@harness ") and "#101" in got[0][1] and "好的，就这样" not in got[0][1]
    assert app._sc_lessons_tick(now + 600) == []               # once a day


def test_a_proposal_carries_the_messages_it_came_from_and_can_be_reworded(tmp_path):
    L = sl.Lessons(tmp_path / "l.json")
    L.set_batch("p", [11, 12, 13])
    got = L.propose("p", ["每页标题的位置和字号一致（#18127 #18136）", "主视觉不用缩小的界面截图"])
    assert len(got) == 1 and got[0]["text"] == "每页标题的位置和字号一致" and got[0]["from"] == [18127, 18136]   # no source: not proposed
    assert L.decide("p", got[0]["id"], True, text="标题位置每页一致，字号按 design system")
    assert L.get("p")["kept"][0]["text"] == "标题位置每页一致，字号按 design system"


def test_old_proposals_without_her_words_are_taken_out_and_asked_again(tmp_path):
    L = sl.Lessons(tmp_path / "l.json")
    c = L._ch("p"); c["pending"] = [{"id": 1, "text": "没有出处", "by": "harness", "at": 1}, {"id": 2, "text": "有出处", "by": "harness", "at": 1, "from": [7]}]
    c["ran_day"] = "2026-11-19"
    assert L.drop_unsourced() == ["p"] and [x["id"] for x in L.get("p")["pending"]] == [2] and L.due("p", "2026-11-19")


def test_two_corrections_spread_over_a_week_are_enough_and_not_asked_about_twice(tmp_path, monkeypatch):
    L = sl.Lessons(tmp_path / "l.json")
    said = scranton_said.Said(tmp_path / "said.json")
    t = time.localtime()
    now = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 9, 0, 0, 0, 0, -1))     # the store drops what is older than 14 real days
    said.add({"id": 300, "sender": "Lu", "text": "@dev 这页的字号太大了，我说过了", "channel": "eon", "timestamp": now - 5 * 86400})
    said.add({"id": 301, "sender": "Lu", "text": "@dev 怎么又是这么大的字，重新做", "channel": "eon", "timestamp": now - 2 * 86400})
    said.add({"id": 302, "sender": "Lu", "text": "@dev 这个不对，不是我要的", "channel": "old", "timestamp": now - 9 * 86400})
    said.add({"id": 303, "sender": "Lu", "text": "@dev 还是没改对，重新做", "channel": "old", "timestamp": now - 8 * 86400})
    monkeypatch.setattr(mcp_bridge, "LESSONS", L)
    monkeypatch.setattr(app, "_sc_said", lambda: said)
    monkeypatch.setattr(app, "_project_channels", lambda: ["eon", "old"])
    monkeypatch.setattr(app, "_paused_channels", lambda: set())
    monkeypatch.setattr(app, "config", {"agents": {"harness": {}}, "team": {}})
    got = app._sc_lessons_tick(now)
    assert all(str(i) in said.items for i in (300, 301))
    assert [ch for ch, _ in got] == ["eon"] and "#300" in got[0][1] and "#301" in got[0][1] and "两次以上" in got[0][1]
    assert app._sc_lessons_tick(now + 86400) == []             # next day: not asked again
    said.add({"id": 304, "sender": "Lu", "text": "@dev 这里间距太挤了，不要这样", "channel": "eon", "timestamp": now + 86400 + 60})
    said.add({"id": 305, "sender": "Lu", "text": "@dev 怎么又挤在一起了，重新做", "channel": "eon", "timestamp": now + 2 * 86400})
    assert app._sc_lessons_tick(now + 2 * 86400 + 3600) == []   # two new ones, but she was asked two days ago
    got = app._sc_lessons_tick(now + 3 * 86400 + 60)
    assert [ch for ch, _ in got] == ["eon"]


def test_a_preference_marked_for_every_project_reaches_the_others(tmp_path):
    L = sl.Lessons(tmp_path / "l.json")
    a = L.add("portfolio", "给 Lu 看页面要发整页上下图")
    L.add("portfolio", "背景图案要放大")
    L.add("deck", "标题位置每页一致")
    assert "整页" not in L.text_for("deck")
    assert L.everywhere("portfolio", a["id"], True) and not L.everywhere("portfolio", 999, True)
    assert "整页" in L.text_for("deck") and "背景图案" not in L.text_for("deck") and "整页" in L.text_for("brand-new")
    assert L.text_for("portfolio").count("整页") == 1
    assert L.get("portfolio")["kept"][0]["all"] is True
    assert L.everywhere("portfolio", a["id"], False) and "整页" not in L.text_for("deck")
    for i in range(sl.MAX_EVERYWHERE):
        x = L.add("p2", f"通用偏好第 {i} 条")
        assert L.everywhere("p2", x["id"], True)
    assert not L.everywhere("portfolio", a["id"], True)        # the list for every project stays short


def test_what_she_dropped_or_kept_is_not_put_to_her_again_in_other_words(tmp_path):
    L = sl.Lessons(tmp_path / "l.json")
    a, b = L.propose("p", ["给 Lu 看页面要发整页上下图，不只发首屏（#101 #102）", "动效先发定帧给 Lu 点头再生成（#103 #104）"])
    L.decide("p", a["id"], True)
    L.decide("p", b["id"], False)
    assert L.dropped("p")[0]["text"].startswith("动效先发定帧")
    again = L.propose("p", ["发给 Lu 的页面要整页上下图，不能只有首屏，因为她说看不全（#201 #202）",
                            "动效要先发定帧给 Lu 点头，再用即梦生成（#203 #204）",
                            "相邻页同类文字位置和字号一致（#205 #206）"])
    assert [x["text"] for x in again] == ["相邻页同类文字位置和字号一致"]
    assert "Lu 否掉的" in sl.request_text("p", [{"id": 1, "text": "x"}], L.get("p")["kept"], "harness", L.dropped("p"))
    assert L.add("p", "动效先发定帧给 Lu 点头再生成") is not None            # what she writes herself is always taken


def test_one_new_correction_is_not_enough_to_ask_again(tmp_path, monkeypatch):
    L = sl.Lessons(tmp_path / "l.json")
    said = scranton_said.Said(tmp_path / "said.json")
    t = time.localtime()
    now = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 9, 0, 0, 0, 0, -1))
    for i, txt in enumerate(("@dev 这页的字号太大了，我说过了", "@dev 怎么又是这么大的字，重新做")):
        said.add({"id": 400 + i, "sender": "Lu", "text": txt, "channel": "eon", "timestamp": now - (i + 1) * 3600})
    monkeypatch.setattr(mcp_bridge, "LESSONS", L)
    monkeypatch.setattr(app, "_sc_said", lambda: said)
    monkeypatch.setattr(app, "_project_channels", lambda: ["eon"])
    monkeypatch.setattr(app, "_paused_channels", lambda: set())
    monkeypatch.setattr(app, "config", {"agents": {"harness": {}}, "team": {}})
    assert len(app._sc_lessons_tick(now)) == 1
    said.add({"id": 402, "sender": "Lu", "text": "@dev 这里间距太挤了，不要这样", "channel": "eon", "timestamp": now + 60})
    assert app._sc_lessons_tick(now + 4 * 86400) == []
