"""Lu, 11-18: a question to her has to show what it is about."""
import mcp_bridge as B


def _setup(monkeypatch):
    monkeypatch.setattr(B, "_owner_name", lambda: "Lu")


def test_a_card_to_lu_without_a_picture_is_not_sent(monkeypatch):
    _setup(monkeypatch)
    _, err = B._picture_check("pm", "@Lu 第 3 页背景用哪个？", ["A. 条纹", "B. 纯色"], "", "slides")
    assert err.startswith("Not sent.") and "image_path" in err
    assert B._picture_check("pm", "@Lu 第 3 页背景用哪个？", ["A. 条纹", "B. 纯色"], "/tmp/ab.png", "slides")[1] == ""


def test_a_plain_question_to_lu_needs_one_too(monkeypatch):
    _setup(monkeypatch)
    assert B._picture_check("pm", "@Lu 这页标题要不要再小一点？", [], "", "slides")[1]
    assert B._picture_check("pm", "@Lu 改好了，19:00 发整套。", [], "", "slides")[1] == ""      # a report, not a question


def test_nothing_to_show_is_said_in_the_first_line(monkeypatch):
    _setup(monkeypatch)
    msg, err = B._picture_check("pm", "无图：这是 GitHub 登录，没有画面\n@Lu 现在登录 bot 账号吗？", ["现在登", "晚点"], "", "slides")
    assert err == "" and msg.startswith("@Lu 现在登录") and "无图" not in msg


def test_teammates_talking_to_each_other_and_lu_herself_are_untouched(monkeypatch):
    _setup(monkeypatch)
    assert B._picture_check("pm", "@dev 这页能 19:00 交吗？", [], "", "slides")[1] == ""
    assert B._picture_check("Lu", "@pm 这页好了吗？", [], "", "slides")[1] == ""
    assert B._picture_check("Scranton", "@Lu 今天做哪几个项目？", ["a", "b"], "", "dm-scranton")[1] == ""


def test_a_question_mark_inside_a_report_is_not_a_question(monkeypatch):
    _setup(monkeypatch)
    assert B._picture_check("pm", "@Lu 你看到的可能是旧缓存？刷新后就是新版。20:30 发整套。", [], "", "slides")[1] == ""
