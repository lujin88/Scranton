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
