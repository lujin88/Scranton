from router import Router


def _r():
    r = Router(["pm", "dev", "qa", "visualqa"], default_mention="none", max_hops=40)
    r.get_targets("lu", "@pm go", "c")
    return r


def test_team_handoffs_are_not_a_loop():
    r = _r()
    chain = [("pm", "dev"), ("dev", "qa"), ("qa", "visualqa"), ("visualqa", "pm")] * 5   # 20 hand-offs
    for a, b in chain:
        assert r.get_targets(a, f"@{b} next", "c") == [b]
    assert not r.is_paused("c")


def test_two_agents_bouncing_pause_after_8():
    r = _r()
    for i in range(8):
        a, b = ("pm", "dev") if i % 2 == 0 else ("dev", "pm")
        assert r.get_targets(a, f"@{b} ?", "c") == [b]
    assert r.get_targets("pm", "@dev ?", "c") == []
    assert r.is_paused("c") and r.pause_hops("c") == 8


def test_overall_budget_still_applies():
    r = Router(["pm", "dev", "qa"], default_mention="none", max_hops=5)
    r.get_targets("lu", "@pm go", "c")
    for a, b in [("pm", "dev"), ("dev", "qa"), ("qa", "pm"), ("pm", "dev"), ("dev", "qa")]:
        r.get_targets(a, f"@{b} x", "c")
    assert r.get_targets("qa", "@pm x", "c") == [] and r.is_paused("c")


def test_you_writing_resets():
    r = _r()
    for i in range(8):
        a, b = ("pm", "dev") if i % 2 == 0 else ("dev", "pm")
        r.get_targets(a, f"@{b} ?", "c")
    r.get_targets("lu", "ok carry on", "c")
    assert r.get_targets("pm", "@dev ?", "c") == ["dev"]
