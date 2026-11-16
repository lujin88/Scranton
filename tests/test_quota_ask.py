import time
from types import SimpleNamespace

import scranton_quota_ask as q

NOW = 1_800_000_000.0


def test_pick_depends_on_time_to_reset():
    other = ("cursor", 75.0)
    # 51 h left: a day+ on pay-per-use → another app first
    t, c = q.question("claude", 98, NOW + 51 * 3600, ["项目经理", "QA"], True, other, now=NOW)
    assert "98%" in t and "@Lu" in t and "51 小时" in t and "项目经理、QA" in t
    assert c[0].startswith("直接换到 Cursor") and c[0].endswith("（推荐）") and len(c) == 3
    # 6 h left: API first, then another app if the key fails
    t, c = q.question("claude", 98, NOW + 6 * 3600, ["项目经理"], True, other, now=NOW)
    assert c[0].startswith("先用备用 API") and "API 不行再自动换到 Cursor" in c[0]
    # 30 min left: wait
    t, c = q.question("claude", 99, NOW + 1800, ["项目经理"], True, other, now=NOW)
    assert c[0].startswith("等重置") and "30 分钟" in t


def test_no_key_and_no_room():
    t, c = q.question("codex", 98, NOW + 6 * 3600, ["visual"], False, ("cursor", 50.0), now=NOW)
    assert [q.classify(x) for x in c] == ["move", "wait"]
    assert q.question("codex", 98, NOW + 6 * 3600, ["visual"], False, None, now=NOW) is None


def test_standin_picks_most_room():
    usage = {"cursor": {"pct": 75}, "codex": {"pct": 4}, "claude": {"pct": 98}}
    assert q.standin("claude", lambda p, m: usage.get(p)) == ("codex", 4.0)
    assert q.standin("claude", lambda p, m: {"cursor": {"pct": 95}}.get(p)) is None


def test_state_roundtrip(tmp_path):
    st = q.State(tmp_path / "qa.json")
    st.approved["claude"] = {"mode": "api", "until": time.time() + 60, "then": "cursor"}
    st.save()
    st2 = q.State(tmp_path / "qa.json")
    assert st2.api_ok("claude") and not st2.api_ok("codex")
    st2.approved["claude"]["until"] = time.time() - 1
    assert not st2.api_ok("claude")


def test_holds_and_api_ok_without_reset_time():
    """Agent Monitor often omits resetsAt; that is not 'already expired'."""
    assert q.holds(None) and q.holds(0) and q.holds(0.0)
    assert q.holds(NOW + 60, now=NOW) and not q.holds(NOW - 1, now=NOW)
    st = q.State.__new__(q.State)
    st.approved = {"codex": {"mode": "api", "until": 0, "then": "cursor"}}
    assert st.api_ok("codex", now=NOW + 10 * 3600)
    st.approved["codex"]["until"] = NOW - 1
    assert not st.api_ok("codex", now=NOW)


def test_tick_asks_once_and_answer_unlocks_api(monkeypatch, tmp_path):
    import asyncio
    import app
    app._SC_QA.clear()
    app._SC_QA.append(q.State(tmp_path / "qa.json"))
    monkeypatch.setattr(app, "config", {"agents": {"pm": {"command": "claude", "label": "项目经理"},
                                                   "dev": {"command": "claude", "label": "开发"}}, "server": {}})
    resets = time.time() + 6 * 3600
    usage = {"claude": {"pct": 98.0, "label": "每周", "resets": resets}, "cursor": {"pct": 75.0, "label": "c", "resets": None}}
    monkeypatch.setattr(app._sc_quota, "provider_usage", lambda p, m="", *a, **k: usage.get(p))
    monkeypatch.setattr(app._sc_keys, "get_key", lambda p: "k" if p == "claude" else "")
    monkeypatch.setitem(app.room_settings, "api_backup_enabled", False)
    posted = []
    monkeypatch.setattr(app, "store", SimpleNamespace(add=lambda *a, **k: posted.append((a, k))))
    asyncio.run(app._sc_qa_tick())
    asyncio.run(app._sc_qa_tick())   # asked once per window
    assert len(posted) == 1
    (sender, text), kw = posted[0]
    assert sender == "Scranton" and kw["msg_type"] == "decision" and "项目经理、开发" in text
    choices = kw["metadata"]["choices"]
    assert choices[0].startswith("先用备用 API")
    assert not app._api_allowed("claude")
    app._sc_qa_apply(kw["metadata"], choices[0])
    assert app._api_allowed("claude") and app._sc_qa().approved["claude"]["then"] == "cursor"
    app._SC_QA.clear()


def test_api_first_without_reset_holds_past_five_hours(monkeypatch, tmp_path):
    """ChatGPT weekly at 97% with resetsAt None: Lu picks API first. Guessing until=now+5h
    used to expire the pick, so reroute sent visual to the intern again (undoing PR #15)."""
    import asyncio
    import app
    qa_path = tmp_path / "qa.json"
    app._SC_QA.clear()
    app._SC_QA.append(q.State(qa_path))
    monkeypatch.setattr(app, "config", {"agents": {"visual": {"command": "codex", "label": "视觉"},
                                                   "pm": {"command": "claude", "label": "项目经理"}},
                                        "server": {}})
    usage = {"codex": {"pct": 98.5, "label": "每周", "resets": None},
             "claude": {"pct": 40.0, "label": "c", "resets": None},
             "cursor": {"pct": 20.0, "label": "cu", "resets": None}}
    monkeypatch.setattr(app._sc_quota, "provider_usage", lambda p, m="", *a, **k: usage.get(p))
    monkeypatch.setattr(app._sc_keys, "get_key", lambda p: "k" if p == "codex" else "")
    monkeypatch.setitem(app.room_settings, "api_backup_enabled", False)
    posted = []
    monkeypatch.setattr(app, "store", SimpleNamespace(add=lambda *a, **k: posted.append((a, k))))
    asyncio.run(app._sc_qa_tick())
    assert posted and posted[0][1]["metadata"]["quota_ask"]["until"] == 0
    app._sc_qa_apply(posted[0][1]["metadata"], posted[0][1]["metadata"]["choices"][0])
    assert app._sc_qa().api_ok("codex")
    # five hours later the week is still at 97%: pick holds, intern handoff stays off
    later = time.time() + 6 * 3600
    asyncio.run(app._sc_qa_tick(now=later))
    assert app._sc_qa().api_ok("codex", now=later)
    assert app._api_allowed("codex")
    # plan actually reset
    usage["codex"] = {"pct": 12.0, "label": "每周", "resets": None}
    asyncio.run(app._sc_qa_tick(now=later + 60))
    assert "codex" not in app._sc_qa().approved
    assert not app._sc_qa().api_ok("codex")
    app._SC_QA.clear()


def test_moved_without_until_stays_while_plan_is_out(monkeypatch, tmp_path):
    """until=0 used to mean 'already due', so the next tick put the teammate back on the dead plan."""
    import asyncio
    import app
    app._SC_QA.clear()
    st = q.State(tmp_path / "qa.json")
    st.moved["visual"] = {"provider": "codex", "model": "", "effort": "", "until": 0}
    app._SC_QA.append(st)
    monkeypatch.setattr(app, "config", {"agents": {"visual": {"command": "codex"}}, "server": {}})
    monkeypatch.setattr(app._sc_quota, "provider_usage",
                        lambda *a, **k: {"pct": 97.0, "label": "每周", "resets": None})
    monkeypatch.setattr(app, "store", SimpleNamespace(add=lambda *a, **k: None))
    asyncio.run(app._sc_qa_tick())
    assert "visual" in app._sc_qa().moved
    app._SC_QA.clear()


def test_apply_rewrites_five_hour_guess(monkeypatch, tmp_path):
    """A card posted before the fix stored until=now+5h. Answering it must not keep that guess."""
    import app
    app._SC_QA.clear()
    app._SC_QA.append(q.State(tmp_path / "qa.json"))
    monkeypatch.setattr(app._sc_quota, "provider_usage",
                        lambda p, m="", *a, **k: {"pct": 98.5, "label": "每周", "resets": None})
    meta = {"quota_ask": {"provider": "codex", "until": time.time() + 5 * 3600, "then": "cursor"}}
    app._sc_qa_apply(meta, "先用备用 API key（按用量付费）到重置")
    assert app._sc_qa().approved["codex"]["until"] == 0
    assert app._sc_qa().api_ok("codex", now=time.time() + 10 * 3600)
    app._SC_QA.clear()
