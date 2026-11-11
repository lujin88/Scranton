import time
from scranton_due import DueBook, parse_due

AG = {"pm", "visual", "dev", "qa"}


def at(h, m, day=0):
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, 0, 0, -1)) + day * 86400


def test_parse_due():
    now = at(10, 0)
    assert parse_due("@visual 改左墙，交 10:30", now) == at(10, 30)
    assert parse_due("@dev 11:45 前交", now) == at(11, 45)
    assert parse_due("@qa ETA: 12:00", now) == at(12, 0)
    assert parse_due("现在 09:00 的活", now) is None
    assert parse_due("交 09:00", at(23, 30)) == at(9, 0, 1)   # tomorrow morning


def test_assign_ack_deliver_overdue(tmp_path):
    b = DueBook(tmp_path / "due.json")
    t0 = at(10, 0)
    assert b.note({"sender": "pm", "text": "@visual v19 只改左墙，交 10:30", "channel": "c", "id": 5, "timestamp": t0}, AG)
    assert "visual" in b.public()
    # 收到 is not a delivery
    b.note({"sender": "visual", "text": "收到，做 v19", "channel": "c", "timestamp": t0 + 60}, AG)
    assert "visual" in b.public()
    # nothing yet at 10:31; told once after the grace
    assert b.overdue(at(10, 31)) == []
    late = b.overdue(at(10, 33))
    assert [h for h, _ in late] == ["visual"] and b.overdue(at(10, 40)) == []
    # a real delivery clears it
    b.note({"sender": "visual", "text": "v19 已交：左墙改直，踢脚线压在红线上，附 3× 对比图和 diff。", "channel": "c", "timestamp": t0 + 2400}, AG)
    assert b.public() == {}


def test_only_pm_or_owner_assigns_and_persists(tmp_path):
    b = DueBook(tmp_path / "due.json")
    b.note({"sender": "dev", "text": "@qa 交 11:00", "channel": "c", "timestamp": at(10, 0)}, AG)
    assert b.public() == {}
    b.note({"sender": "Lu", "text": "@dev 交 11:00", "channel": "c", "timestamp": at(10, 0)}, AG, owner="Lu")
    assert "dev" in DueBook(tmp_path / "due.json").public()
