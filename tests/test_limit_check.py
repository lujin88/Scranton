import json, time
import scranton_quota as q
import wrapper_unix as wu


def _usage(tmp_path, data):
    f = tmp_path / "usage.json"
    f.write_text(json.dumps(data))
    return str(f)


def test_warning_lines_are_not_a_limit():
    for line in ("⚠ Heads up, you have less than 10% of your weekly limit left",
                 "Approaching usage limit · resets at 3pm", "You've used 90% of your weekly limit"):
        assert wu._WARNING.search(line)
    assert not wu._WARNING.search("Error: You've hit your usage limit")


def test_model_limit_screens():
    rx = dict((k, r) for k, r, _ in wu._PROBLEMS)["model_limit"]
    assert rx.search("Switch to a different model or set a Spend Limit to continue with Gemini.")
    assert rx.search("⚠ Individual quota reached. Please upgrade your subscription")


def test_cursor_pools(tmp_path):
    now = time.time()
    f = _usage(tmp_path, {"cursor": {"updatedAt": now * 1000, "windows": [
        {"label": "Cursor models", "usedPercent": 75, "resetsAt": now + 9e5},
        {"label": "Other models", "usedPercent": 100, "resetsAt": now + 9e5}]}})
    assert q.provider_usage("cursor", "gemini-4-carbon-low", f)["pct"] == 100
    assert q.provider_usage("cursor", "composer-2.5", f)["pct"] == 75
    assert q.model_fallback("cursor", "gemini-4-carbon-low", f) == "composer-2.5"
    assert q.model_fallback("cursor", "composer-2.5", f) is None


def test_codex_at_93_is_not_out(tmp_path):
    now = time.time()
    f = _usage(tmp_path, {"codex": {"updatedAt": now * 1000, "windows": [{"label": "每周", "usedPercent": 93, "resetsAt": now + 3600}]}})
    assert q.provider_usage("codex", "", f)["pct"] < 99
    assert q.provider_usage("gemini", "", f) is None   # no numbers: the screen decides


def test_reset_parsing():
    now = 1_000_000.0
    assert q.reset_from_text("Resets in 155h21m9s.", now) == now + 155 * 3600 + 21 * 60
    assert q.reset_from_text("nothing here", now) is None


def test_quoted_limit_and_api_credit():
    assert wu._QUOTED.search("webdev 每 30 分钟发一次的「hit its usage limit」，最后一条是 06:10")
    assert not wu._QUOTED.search("Error: You've hit your usage limit")
    rx = dict((k, r) for k, r, _ in wu._PROBLEMS)["api_credit"]
    assert rx.search("⎿  Credit balance too low · Add funds:")


def test_limit_verdict_needs_numbers_or_time():
    import app
    app._LIMIT_UNKNOWN.clear()
    # numbers: under 99% is room, at 99% go on
    assert app._limit_verdict("pm", "limit", {"pct": 79.0}) == "ignore"
    assert app._limit_verdict("pm", "limit", {"pct": 99.0}) == "go on"
    # no numbers: first sighting is never a stop, the check 10 min later is
    assert app._limit_verdict("qa", "limit", None, now=1000) == "ignore"
    assert app._limit_verdict("qa", "limit", None, now=1100) == "ignore"
    assert app._limit_verdict("qa", "limit", None, now=1700) == "go on"
    # numbers again clear the memory
    assert app._limit_verdict("qa", "limit", {"pct": 50}, now=1800) == "ignore"
    assert app._limit_verdict("qa", "limit", None, now=1900) == "ignore"
    assert app._limit_verdict("pm", "api_credit", None) == "go on"


def test_failed_check_is_not_a_stop(monkeypatch):
    import wrapper
    def boom(*a, **k):
        raise OSError("server busy")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert wrapper._ask_limit_check(1, "t", {"channel": "x", "thread": None}, "limit") == "ignore"
