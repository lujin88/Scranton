"""Lu, 11-17: reminders only for the projects she picked today; none before she answers."""
import time
import scranton_today as T

CH = ["lu-portfolio", "client-advisory-slid", "contour-slide", "contour", "dm-pm", "agent-monitor"]


def _t(tmp_path):
    return T.Today(tmp_path / "today.json")


def test_nothing_is_active_before_she_answers(tmp_path):
    t = _t(tmp_path)
    assert t.chosen() is None
    assert t.quiet(CH) == set(CH)


def test_asks_once_a_day(tmp_path):
    t = _t(tmp_path)
    now = time.mktime((2026, 11, 17, 9, 0, 0, 0, 0, -1))
    assert t.need_ask(now) is True
    assert t.need_ask(now + 3600) is False
    assert t.need_ask(now + 24 * 3600) is True


def test_only_chosen_channels_get_reminders(tmp_path):
    t = _t(tmp_path)
    kind, chans = T.parse("@Scranton 今天做 client-advisory-slid、contour-slide", CH)
    assert (kind, chans) == ("set", ["client-advisory-slid", "contour-slide"])
    t.choose(chans)
    assert t.active("client-advisory-slid") and t.active("contour-slide")
    assert not t.active("lu-portfolio") and not t.active("contour") and not t.active("dm-pm")
    assert t.need_ask() is False        # answered: don't ask again today


def test_card_click_reply_is_understood(tmp_path):
    assert T.parse("@Scranton A：client-advisory-slid", CH) == ("set", ["client-advisory-slid"])
    assert T.parse("@Scranton E：全部项目", CH)[0] == "all"
    assert T.parse("@Scranton F：今天不做项目", CH)[0] == "none"


def test_add_keeps_what_was_chosen(tmp_path):
    t = _t(tmp_path)
    t.choose(["client-advisory-slid"])
    kind, chans = T.parse("@scranton 加上 lu-portfolio", CH)
    assert kind == "add"
    assert t.choose(chans, add=True) == ["client-advisory-slid", "lu-portfolio"]


def test_all_and_none(tmp_path):
    t = _t(tmp_path)
    t.choose([], all_=True)
    assert t.quiet(CH) == set()
    t.choose([])
    assert t.quiet(CH) == set(CH) and t.chosen() == (False, [])


def test_choice_lasts_through_the_night_and_ends_at_five(tmp_path):
    t = _t(tmp_path)
    day = time.mktime((2026, 11, 17, 15, 0, 0, 0, 0, -1))
    t.choose(["contour-slide"], now=day)
    assert t.active("contour-slide", time.mktime((2026, 11, 18, 3, 0, 0, 0, 0, -1)))
    assert not t.active("contour-slide", time.mktime((2026, 11, 18, 6, 0, 0, 0, 0, -1)))


def test_unclear_text_changes_nothing(tmp_path):
    assert T.parse("@Scranton 你好", CH) == ("", [])
    assert "项目名" in T.help_text(None, CH)


def test_question_offers_recent_projects_and_wakes_no_teammate():
    text, choices = T.question("Lu", ["client-advisory-slid", "lu-portfolio"])
    assert text.startswith("@Lu ") and "@pm" not in text
    assert choices[:2] == ["client-advisory-slid", "lu-portfolio"] and T.ALL in choices and T.NONE in choices


MINI = ["scranton-feedback", "lu-portfolio", "agent-monitor", "ai-pet", "eon-slide", "contour-slide",
        "client-advisory-slid", "man-screen"]


def test_names_the_way_lu_says_them():
    assert T.parse("今天主要就做 client advisory slides，然后来得及的话做 MAN screen", MINI) == \
        ("set", ["client-advisory-slid", "man-screen"])
    assert T.parse("今天做 client advisory", MINI) == ("set", ["client-advisory-slid"])
    assert T.parse("加上 portfolio 和 contour", MINI)[1] == ["contour-slide"]      # "portfolio" alone: not a first word
    assert T.parse("加上 lu portfolio", MINI) == ("add", ["lu-portfolio"])
    assert T.parse("今天做 slides", MINI) == ("", [])                              # two projects end in slide: ask


def test_the_rest_not_today_never_wipes_the_choice():
    assert T.parse("别的今天先不要做", MINI) == ("keep", [])
    assert T.parse("别的今天都不做", MINI) == ("keep", [])


def test_talk_in_the_scranton_dm_is_not_a_today_command():
    """The 1-on-1 is also where sign-in and stuck-app notes land. Those lines must not
    pick or wipe today's projects (11-18: 'Cursor 停了' / '停在登录页' became 今天不做)."""
    for line in ("Cursor 停了", "停在登录页", "我去休息一下", "所有的图都要描边",
                 "that's all", "agent monitor 额度满了", "好的我去登录"):
        assert not T.is_command(line), line
        assert T.parse(line, MINI) == ("", []), line


def test_real_today_commands_still_parse():
    assert T.is_command("今天做 client advisory slides")
    assert T.is_command("今天主要就做 client advisory slides，然后来得及的话做 MAN screen")
    assert T.is_command("加上 lu-portfolio")
    assert T.is_command("@Scranton A：client-advisory-slid")
    assert T.is_command("@Scranton E：全部项目")
    assert T.is_command("@Scranton F：今天不做项目")
    assert T.parse("全部项目", MINI) == ("all", [])
    assert T.parse("全部", MINI) == ("all", [])
    assert T.parse("今天不做", MINI) == ("none", [])
    assert T.parse("今天不做项目", MINI) == ("none", [])


def test_casual_dm_does_not_wipe_a_choice(tmp_path):
    t = _t(tmp_path)
    t.choose(["client-advisory-slid", "man-screen"])
    kind, chans = T.parse("Cursor 停了", MINI)
    assert (kind, chans) == ("", [])
    assert t.chosen() == (False, ["client-advisory-slid", "man-screen"])
