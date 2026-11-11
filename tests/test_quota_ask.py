import time
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
    monkeypatch.setattr(app.store, "add", lambda *a, **k: posted.append((a, k)))
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
