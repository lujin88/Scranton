import json, time
import scranton_quota as q

CFG_AGENTS = {"visual": {}, "motion": {}, "visintern": {}, "motionintern": {}, "pm": {}}


def _cfg(tmp_path, windows, age=0, **extra):
    f = tmp_path / "usage.json"
    f.write_text(json.dumps({"codex": {"windows": windows, "updatedAt": (time.time() - age) * 1000}}))
    return {"agents": CFG_AGENTS, "team": {"quota_handoff": {"usage_file": str(f), **extra}}}


def setup_function(_):
    q._state.update(low=False, percent=None, label="")


def test_low_moves_visual_and_motion(tmp_path):
    cfg = _cfg(tmp_path, [{"label": "5 小时", "usedPercent": 92, "resetsAt": time.time() + 3600},
                          {"label": "每周", "usedPercent": 40, "resetsAt": None}])
    assert q.check(cfg) == (True, True)
    t, moved = q.reroute(cfg, ["visual", "motion", "pm"], "lu-portfolio", "Lu")
    assert t == ["visintern", "motionintern", "pm"]
    assert moved == {"visual": "visintern", "motion": "motionintern"}
    assert "92%" in q.notice(cfg, True) and q.notice(cfg, True).startswith("@pm")


def test_dm_is_left_alone(tmp_path):
    cfg = _cfg(tmp_path, [{"label": "5 小时", "usedPercent": 99, "resetsAt": None}])
    q.check(cfg)
    assert q.reroute(cfg, ["visual"], "dm-visual", "Lu") == (["visual"], {})


def test_hysteresis_and_recovery(tmp_path):
    cfg = _cfg(tmp_path, [{"label": "5 小时", "usedPercent": 91, "resetsAt": None}])
    q.check(cfg)
    cfg = _cfg(tmp_path, [{"label": "5 小时", "usedPercent": 85, "resetsAt": None}])
    assert q.check(cfg) == (True, False)       # between 80 and 90: stays moved
    cfg = _cfg(tmp_path, [{"label": "5 小时", "usedPercent": 70, "resetsAt": None}])
    assert q.check(cfg) == (False, True)


def test_stale_reset_or_missing_means_normal(tmp_path):
    assert q.check(_cfg(tmp_path, [{"usedPercent": 99}], age=3600))[0] is False
    assert q.check(_cfg(tmp_path, [{"usedPercent": 99, "resetsAt": time.time() - 10}]))[0] is False
    cfg = {"agents": CFG_AGENTS, "team": {"quota_handoff": {"usage_file": str(tmp_path / "nope.json")}}}
    assert q.check(cfg)[0] is False


def test_disabled_and_missing_intern(tmp_path):
    cfg = _cfg(tmp_path, [{"usedPercent": 99}], enabled=False)
    assert q.check(cfg)[0] is False
    cfg = _cfg(tmp_path, [{"usedPercent": 99}])
    q.check(cfg)
    cfg["agents"] = {"visual": {}}
    assert q.reroute(cfg, ["visual"], "general", "Lu") == (["visual"], {})
