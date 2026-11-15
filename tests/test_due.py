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


def test_long_ack_is_not_a_delivery(tmp_path):
    b = DueBook(tmp_path / "due.json")
    t0 = at(10, 0)
    b.note({"sender": "pm", "text": "@visual v7 改色调，交 10:30", "channel": "c", "timestamp": t0}, AG)
    b.note({"sender": "visual", "text": "@pm 收到 #6892。以 visual v6 为底，v7 改回 A 的米白墙、棕木地板、黄绿藤，并恢复浓密层叠藤幔；保持 4 窗。",
            "channel": "c", "timestamp": t0 + 30}, AG)
    assert "visual" in b.public()
    b.note({"sender": "visual", "text": "@pm v7 已交，三张并排在附图。", "channel": "c", "timestamp": t0 + 900}, AG)
    assert b.public() == {}


def _assigned(tmp_path):
    b = DueBook(tmp_path / "due.json")
    t0 = at(10, 0)
    b.note({"sender": "pm", "text": "@dev 修这个，交 15:00", "channel": "c", "id": 1, "timestamp": t0}, AG)
    assert "dev" in b.public()
    return b, t0


def test_wrapper_status_is_not_a_delivery(tmp_path):
    """wrapper._post and app store.add speak as the teammate. Those lines used to clear 交 HH:MM
    because they are long and not 收到 — so the PM was never told when the work actually overran."""
    samples = [
        "I can't read this yet: my terminal is waiting on a question: “Allow?”. "
        "Open my terminal to answer it, and I'll pick this up right after.",
        "I stopped: my Claude plan has hit its usage limit. @ me again after it resets, "
        "or switch me to another app: Settings → Agents → me → Runs on.",
        "I stopped without replying, even after a reminder. Open my terminal to see where I am, or @ me again.",
        'My screen hasn\'t changed for 12 minutes while I\'m "working": a command may be stuck '
        "(last line: ffmpeg -i in.mp4). I'll stop it myself at 60 minutes; open my terminal to stop it sooner.",
        "Stopped a command that was stuck for 60 minutes (pressed Esc). Picking up again.",
        "Your message didn't reach me after 3 tries. Restart me: Settings → Agents → me → Restart.",
        "Claude 额度用完了，按 Lu 的选择，换到 Cursor 接着干，11-15 08:00 换回来。",
        "为了把 Claude 额度留给项目经理和 QA（Lu 定），换到 Cursor 接着干，11-15 08:00 换回来。",
        "备用 API key 用不了，按 Lu 的选择，换到 Cursor 接着干，11-15 08:00 换回来。",
        "My ChatGPT plan has hit its limit, so I'm carrying on with the backup API key until it resets.",
        "The backup API key has no credit left, so I'm going back to the plan. "
        "Add funds with the provider, or remove the key in Settings → Connections.",
        "Composer 2.5 has used up its quota, but the plan still has room on other models: "
        "I'm carrying on with Composer 2 and will switch back after it resets (11-15 08:00).",
        "I hit an error from Claude and stopped. Open my terminal to see it, or restart me.",
    ]
    for text in samples:
        b, t0 = _assigned(tmp_path)
        b.note({"sender": "dev", "text": text, "channel": "c", "timestamp": t0 + 60}, AG)
        assert "dev" in b.public(), text
        # still told once when the time passes
        late = b.overdue(at(15, 3))
        assert [h for h, _ in late] == ["dev"], text


def test_status_with_a_pr_still_counts_as_delivery(tmp_path):
    b, t0 = _assigned(tmp_path)
    b.note({"sender": "dev", "text": "I stopped fighting the rebase; PR #42 is up.",
            "channel": "c", "timestamp": t0 + 60}, AG)
    assert b.public() == {}


def test_long_real_reply_still_counts_as_delivery(tmp_path):
    b, t0 = _assigned(tmp_path)
    b.note({"sender": "dev", "text": "左墙改直了，踢脚线压在红线上，三张对比图在附图，"
            "踢脚线和窗框的接缝也对上了，颜色按 v6 米白。",
            "channel": "c", "timestamp": t0 + 60}, AG)
    assert b.public() == {}
