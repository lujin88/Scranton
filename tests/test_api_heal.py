import asyncio
import app


def test_switch_off_by_default_and_heal_brings_back(monkeypatch):
    monkeypatch.setitem(app.room_settings, "api_backup_enabled", False)
    assert app._api_backup_on() is False
    ended, restarted = [], []
    monkeypatch.setattr(app._sc_keys, "all_on_api", lambda: {"pm": {"provider": "claude", "since": 0}})
    monkeypatch.setattr(app._sc_keys, "end_api", lambda n: ended.append(n) or True)

    async def fake_restart(n):
        restarted.append(n)
    monkeypatch.setattr(app, "_sc_restart_quiet", fake_restart)
    assert asyncio.run(app._sc_api_heal()) == ["pm"]
    assert ended == ["pm"] and restarted == ["pm"]


def test_heal_keeps_key_when_on_and_plan_really_out(monkeypatch):
    monkeypatch.setitem(app.room_settings, "api_backup_enabled", True)
    monkeypatch.setattr(app._sc_keys, "all_on_api", lambda: {"pm": {"provider": "claude", "since": 0}})
    monkeypatch.setattr(app._sc_quota, "provider_usage", lambda *a, **k: {"pct": 100, "label": "w", "resets": None})
    monkeypatch.setattr(app._sc_keys, "end_api", lambda n: (_ for _ in ()).throw(AssertionError("should stay")))
    assert asyncio.run(app._sc_api_heal()) == []
