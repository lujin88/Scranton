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


def test_a_merge_question_inside_a_list_is_not_sent(monkeypatch):
    _setup(monkeypatch)
    batch = ("@Lu 你离开这段时间要你定的 3 件：\n1. 行 70 首页时间线 PR #204：qa、visualqa 都过了\nA. 合，上线（推荐）\nB. 先不合\n"
             "2. 行 6 用哪张图\nA. 派对静物\nB. 礼物盒")
    err = B._merge_in_batch("pm", batch, [])
    assert err.startswith("Not sent.") and "ONE pull request" in err
    assert B._merge_in_batch("pm", "@Lu 定 2 件：\n1. 用哪张图\nA. 派对静物\nB. 礼物盒\n2. 标题\nA. 合并成一行\nB. 两行", []) == ""
    assert B._merge_in_batch("pm", "@Lu 行 56 PR #197，HEAD 9c78b0e（图左现在｜右旋转）。点合后 pm 合并。", ["合 (推荐)", "先不合"]) == ""
    assert B._merge_in_batch("pm", batch.replace("@Lu", "@dev"), []) == ""
    assert B._merge_in_batch("Lu", batch, []) == ""


def test_a_card_about_something_that_moves_needs_it_moving(monkeypatch):
    _setup(monkeypatch)
    card = "@Lu 行 36 CA07 曲线卡 PR #223，HEAD 194cc4c：视频停住那帧比原图偏蓝。"
    opts = ["接受现在的视频，合上线 (推荐)", "先用静图"]
    assert B._motion_needs_motion("pm", card, opts, "/tmp/left-right.png").startswith("Not sent.")
    assert B._motion_needs_motion("pm", card, opts, "/tmp/play.gif\n/tmp/left-right.png") == ""
    assert B._motion_needs_motion("pm", "静图：只问停住那一帧的颜色\n" + card, opts, "/tmp/left-right.png") == ""
    assert B._motion_needs_motion("pm", "@Lu 行 12 BMW 整页 PR #224，HEAD 2de6b4c。", ["A. 合 (推荐)", "B. 先不合"], "/tmp/page.png") == ""
    assert B._motion_needs_motion("pm", card, [], "/tmp/left-right.png") == ""      # not a card: the picture rule already covers questions


def test_a_merge_card_says_how_to_undo_and_what_was_not_checked(monkeypatch):
    _setup(monkeypatch)
    card = "@Lu 行 16 Gratula PR #237，HEAD 06e7909：qa、legal、visualqa 都签了。图左 A 稿｜右我们。"
    opts = ["合 (推荐)", "先不合"]
    err = B._merge_card_gaps("dev", card, opts)
    assert err.startswith("Not sent.") and "撤回" in err and "没验" in err
    one = B._merge_card_gaps("dev", card + "\n撤回：revert 这个 PR，约 5 分钟重新部署", opts)
    assert "没验" in one and "「撤回：" not in one
    full = card + "\n撤回：revert 这个 PR，约 5 分钟重新部署\n没验：尾线的实时观感，visualqa 只签了静态"
    assert B._merge_card_gaps("dev", full, opts) == ""
    assert B._merge_card_gaps("dev", full.replace("没验：尾线的实时观感，visualqa 只签了静态", "没验：无"), ["A. 合 (推荐)", "B. 先不合"]) == ""
    assert B._merge_card_gaps("pm", "@Lu 行 6 用哪张图（PR #12 里两版都有）", ["派对静物", "礼物盒"]) == ""      # not a merge card
    assert B._merge_card_gaps("pm", "@Lu 标题要不要合并成一行？", ["合并成一行", "保持两行"]) == ""             # no pull request
    assert B._merge_card_gaps("dev", card.replace("@Lu", "@qa"), opts) == ""
