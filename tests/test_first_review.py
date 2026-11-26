"""A PR is read by the first reviewer before QA (Lu, 11-26)."""
import time
import mcp_bridge as B

URL = "https://github.com/lujin88/Party-Planner/pull/93"


class _Store:
    def __init__(self, msgs): self.msgs = msgs
    def get_recent(self, count=50, channel=None): return [m for m in self.msgs if m.get("channel") == channel][-count:]


def _setup(monkeypatch, msgs=(), agents=("review", "qa", "dev")):
    monkeypatch.setattr(B, "config", {"agents": {a: {} for a in agents},
                                      "team": {"lead": "pm", "first_review": {"agent": "review", "final": "qa"}}})
    monkeypatch.setattr(B, "store", _Store(list(msgs)))
    monkeypatch.setattr(B, "_owner_name", lambda: "Lu")


def _m(sender, text, ch="gratula"):
    return {"sender": sender, "text": text, "channel": ch, "timestamp": time.time()}


def test_a_new_pr_goes_to_the_first_reviewer(monkeypatch):
    _setup(monkeypatch)
    err = B._first_review_gate("dev", f"@qa 行 8 做完，请审｜{URL}", "gratula")
    assert err.startswith("Not sent. PR #93") and "@review instead of @qa" in err and "ask @pm" in err
    assert B._first_review_gate("dev", f"@review 行 8 做完，请审｜{URL}", "gratula") == ""


def test_after_the_first_review_passed_it_reaches_qa(monkeypatch):
    _setup(monkeypatch, [_m("review", f"初审通过 abc1234\n没查：Safari｜{URL}")])
    assert B._first_review_gate("dev", f"@qa 初审过了，请审｜{URL}", "gratula") == ""
    _setup(monkeypatch, [_m("review", f"初审要改 abc1234：漏了空状态｜{URL}")])
    assert B._first_review_gate("dev", f"@qa 请审｜{URL}", "gratula").startswith("Not sent.")


def test_fixes_for_qas_own_findings_go_straight_back(monkeypatch):
    _setup(monkeypatch, [_m("qa", f"@dev 行 8 #93 QA 要改 abc1234：…｜{URL}#issuecomment-1")])
    assert B._first_review_gate("dev", f"@qa 改好了，新 HEAD def5678｜{URL}", "gratula") == ""


def test_another_pr_or_another_repo_does_not_count(monkeypatch):
    _setup(monkeypatch, [_m("review", "初审通过 abc｜https://github.com/lujin88/Party-Planner/pull/92"),
                         _m("qa", "QA 通过｜https://github.com/lujin88/LuJin-Portfolio/pull/93")])
    assert B._first_review_gate("dev", f"@qa 请审｜{URL}", "gratula").startswith("Not sent.")


def test_who_is_let_through(monkeypatch):
    _setup(monkeypatch)
    for who in ("review", "qa", "pm", "Lu"):
        assert B._first_review_gate(who, f"@qa 请审｜{URL}", "gratula") == ""
    assert B._first_review_gate("dev", "@qa 这个测试为什么在 main 上也挂？", "gratula") == ""     # no PR link
    assert B._first_review_gate("dev", f"@visualqa 请验｜{URL}", "gratula") == ""               # not to QA


def test_off_when_there_is_no_reviewer(monkeypatch):
    _setup(monkeypatch, agents=("qa", "dev"))
    assert B._first_review_gate("dev", f"@qa 请审｜{URL}", "gratula") == ""
