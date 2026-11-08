import pytest
import scranton_team as t


def _cfg():
    return {"agents": {"pm": {"command": "claude"}, "dev": {"command": "codex"}}}


def test_claude_takes_max_codex_does_not(monkeypatch, tmp_path):
    monkeypatch.setattr(t, "OVERRIDES", tmp_path / "teammates.json")
    c = _cfg()
    assert t.set_override("pm", "effort", "max", c)["effort"] == "max"
    assert t.set_override("dev", "effort", "xhigh", c)["effort"] == "xhigh"
    with pytest.raises(ValueError):
        t.set_override("dev", "effort", "max", c)


def test_profile_lists_efforts_per_app(monkeypatch, tmp_path):
    monkeypatch.setattr(t, "OVERRIDES", tmp_path / "teammates.json")
    c = _cfg()
    assert t.profile("pm", c, {}, [])["efforts"][-1] == "max"
    assert "max" not in t.profile("dev", c, {}, [])["efforts"]
    assert all("latest" not in m[1] for m in t.profile("pm", c, {}, [])["models"])
