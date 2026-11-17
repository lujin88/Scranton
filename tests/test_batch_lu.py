"""Lu, 11-17 (A/D/E): her bursts reach the PM as one message; Cursor's per-reply connections
aren't announced as disconnects; a sign-in screen is recognised."""
import asyncio

import app
import wrapper_unix


def _setup(monkeypatch, wait=0.05):
    monkeypatch.setattr(app, "config", {"team": {"mentions_from": "pm", "batch_seconds": wait},
                                        "agents": {"pm": {"command": "claude"}, "webdev": {"command": "agent"},
                                                   "dev": {"command": "claude"}}})
    monkeypatch.setitem(app.room_settings, "username", "Lu")
    app._sc_batches.clear()
    got = []

    async def wake(target, msg, channel, prompt="", thread=None):
        got.append((target, msg, channel, thread))
    monkeypatch.setattr(app, "_wake_teammate", wake)
    return got


def test_only_lu_to_pm_is_held(monkeypatch):
    _setup(monkeypatch)
    ok = app._sc_batchable
    assert ok("Lu", "pm", "chat", "@pm 改一下", "", "c")
    assert not ok("Lu", "dev", "chat", "@dev 改一下", "", "c")       # other teammates: at once
    assert not ok("visual", "pm", "chat", "@pm 交了", "", "c")       # teammates' reports: at once
    assert not ok("Lu", "pm", "chat", "@pm 紧急：线上挂了", "", "c")   # urgent: at once
    monkeypatch.setitem(app.config["team"], "batch_seconds", 0)
    assert not ok("Lu", "pm", "chat", "@pm 改一下", "", "c")         # switched off


def test_a_burst_arrives_as_one(monkeypatch):
    got = _setup(monkeypatch)

    async def run():
        app._sc_batch_add("pm", "Lu", "@pm 第 3 页标题太大", "slides", None)
        await asyncio.sleep(0.02)
        app._sc_batch_add("pm", "Lu", "@pm 算了，标题不动，改副标题", "slides", None)
        app._sc_batch_add("pm", "Lu", "@pm MagicPath 能用吗", "man-screen", None)
        await asyncio.sleep(0.2)
    asyncio.run(run())
    assert len(got) == 2                                             # one per channel
    slides = next(g for g in got if g[2] == "slides")[1]
    assert slides.startswith("Lu: (2 messages") and "1) @pm 第 3 页" in slides and "2) @pm 算了" in slides
    assert next(g for g in got if g[2] == "man-screen")[1] == "Lu: @pm MagicPath 能用吗"   # a single one is unchanged


def test_never_waits_more_than_the_cap(monkeypatch):
    got = _setup(monkeypatch, wait=0.2)
    monkeypatch.setattr(app, "BATCH_MAX", 0.3)

    async def run():
        for i in range(6):                       # she keeps typing every 0.1 s
            app._sc_batch_add("pm", "Lu", f"@pm {i}", "c", None)
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.3)
    asyncio.run(run())
    assert len(got) >= 2 and sum(g[1].count("@pm") for g in got) == 6     # nothing lost


def test_cursor_connections_are_not_disconnects(monkeypatch):
    _setup(monkeypatch)
    assert app._per_turn_agent("webdev-3") and app._per_turn_agent("webdev")
    assert app._per_turn_agent("dev-2") and not app._per_turn_agent("dev") and not app._per_turn_agent("pm")


def test_sign_in_screen():
    assert wrapper_unix.is_signin("You are not signed in.\n 1. Sign in with Google (OAuth)\n 2. API key")
    assert not wrapper_unix.is_signin("Do you want to proceed?\n 1. Yes\n 2. No")
    t = wrapper_unix.problem_text("signin", "Antigravity", "", "agentchattr-visintern")
    assert "tmux attach -t agentchattr-visintern" in t and "Antigravity" in t
