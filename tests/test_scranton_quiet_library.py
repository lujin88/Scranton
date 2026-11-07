"""Quiet hours note for agents, and built-in roles coming back from the Library."""
import datetime, json
import wrapper, scranton_team as t


def test_quiet_note_inside_and_outside(tmp_path, monkeypatch):
    monkeypatch.setattr(wrapper, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "quiet-hours.json").write_text(json.dumps({"enabled": True, "from": "22:00", "to": "08:00"}))
    assert "QUIET HOURS" in wrapper._quiet_note(datetime.datetime(2026, 11, 8, 23, 30))
    assert "QUIET HOURS" in wrapper._quiet_note(datetime.datetime(2026, 11, 8, 7, 59))
    assert wrapper._quiet_note(datetime.datetime(2026, 11, 8, 8, 0)) == ""
    (tmp_path / "data" / "quiet-hours.json").write_text(json.dumps({"enabled": False, "from": "22:00", "to": "08:00"}))
    assert wrapper._quiet_note(datetime.datetime(2026, 11, 8, 23, 30)) == ""


def test_quiet_hours_validates(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "QUIET", tmp_path / "q.json")
    assert t.set_quiet_hours(True, "21:30", "07:00")["from"] == "21:30"
    try:
        t.set_quiet_hours(True, "25:00", "07:00")
        assert False
    except ValueError:
        pass


def test_removed_role_goes_to_library_and_back(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "OVERRIDES", tmp_path / "teammates.json")
    monkeypatch.setattr(t, "stop", lambda *a, **k: None)
    cfg = {"agents": {"copy": {"label": "UX 文案", "command": "claude", "cwd": "~/x", "role": "UX Copywriter: text"}}}
    t.delete_agent("copy", cfg, tmp_path)
    assert "copy" not in cfg["agents"]
    lib = t.library(cfg)
    assert lib and lib[0]["handle"] == "copy" and lib[0]["app"] == "Claude"
    t.restore_agent("copy", cfg)
    assert "copy" in cfg["agents"] and not t.library(cfg)
    assert "copy" not in json.loads((tmp_path / "teammates.json").read_text()).get("_removed", [])
