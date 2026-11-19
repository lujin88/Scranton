import json
import time

import app
import mcp_bridge
import scranton_lessons as sl
import scranton_said


def test_proposed_then_kept_then_handed_to_readers(tmp_path, monkeypatch):
    L = sl.Lessons(tmp_path / "lessons.json")
    monkeypatch.setattr(mcp_bridge, "LESSONS", L)
    got = L.propose("deck", ["- 每页标题的位置和字号一致", "2. 主视觉不用缩小的界面截图", "每页标题的位置和字号一致", "x"], by="harness")
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
        assert L.add("p", f"偏好第 {i} 条的内容")
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
    assert got[0]["text"] == "每页标题的位置和字号一致" and got[0]["from"] == [18127, 18136]
    assert got[1]["from"] == [11, 12, 13]                       # none named: the day's corrections
    assert L.decide("p", got[0]["id"], True, text="标题位置每页一致，字号按 design system")
    assert L.get("p")["kept"][0]["text"] == "标题位置每页一致，字号按 design system"
