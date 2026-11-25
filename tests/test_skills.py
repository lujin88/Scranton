import json
from pathlib import Path

import scranton_skills as S


def _install(root: Path, name: str, front: str | None = None):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {front or name}\ndescription: x\n---\nbody\n", "utf-8")


def _cfg(root, **allow):
    return {"team": {"owner": "Lu", "skills": {"limit": True, "updater": "harness", "dirs": [str(root)], "allow": allow}}}


def test_everything_not_listed_is_off_for_that_teammate(tmp_path):
    root = tmp_path / "skills"
    for n in ("impeccable", "unslop", "prototype", "grill-me", "tdd"):
        _install(root, n)
    _install(root, "emil", "emil-design-eng")                      # folder and skill name differ
    cfg = _cfg(root, visual=["impeccable", "unslop", "prototype"], webdev=["emil-design-eng"])
    found = S.installed([str(root)])
    st = S.claude_settings(S.allowed(cfg, "visual"), found, False)
    assert set(st["skillOverrides"]) == {"grill-me", "tdd", "emil", "emil-design-eng"} and set(st["skillOverrides"].values()) == {"off"}
    assert "Skill(grill-me)" in st["permissions"]["deny"] and "Bash(npx skills update:*)" in st["permissions"]["deny"]
    assert "emil" not in S.claude_settings(S.allowed(cfg, "webdev"), found, False)["skillOverrides"]   # its own skill stays, under either name
    assert S.claude_settings([], found, True)["permissions"]["deny"] == [f"Skill({n})" for n in sorted(found)]  # the updater may update
    assert len(S.claude_settings(S.allowed(cfg, "copy"), found, False)["skillOverrides"]) == 7          # not listed: none


def test_launch_arguments_per_app(tmp_path):
    root = tmp_path / "skills"
    for n in ("animate", "grill-me"):
        _install(root, n)
    cfg = _cfg(root, motion=["animate"], dev=["tdd"])
    a = S.launch_args(cfg, "motion", "codex", tmp_path)
    assert a[0] == "-c" and a[1] == 'skills.config=[{path=' + json.dumps(str(root / "grill-me" / "SKILL.md")) + ',enabled=false}]'
    import tomllib
    assert tomllib.loads(a[1])["skills"]["config"][0]["enabled"] is False                               # valid TOML for -c
    c = S.launch_args(cfg, "dev", "claude", tmp_path)
    assert c[0] == "--settings" and json.loads(Path(c[1]).read_text())["skillOverrides"] == {"animate": "off", "grill-me": "off"}
    assert S.launch_args(cfg, "webdev", "agent", tmp_path) == []                                        # Cursor: no switch
    assert S.launch_args({"team": {}}, "dev", "claude", tmp_path) == []                                 # not limited: untouched


def test_the_sentence_in_the_brief(tmp_path):
    cfg = _cfg(tmp_path, pm=["handoff", "to-questionnaire"], harness=["retro"])
    line = S.brief_line(cfg, "pm")
    assert line.startswith("Skills: yours are handoff, to-questionnaire.") and "without being asked" in line and "Ignore every other installed skill" in line
    assert "Never run `npx skills add`" in S.brief_line(cfg, "pm")
    assert "Only you may run `npx skills update`" in S.brief_line(cfg, "harness") and "after Lu approved" in S.brief_line(cfg, "harness")
    assert S.brief_line(cfg, "copy").startswith("Skills: you have none")
    assert S.brief_line({"team": {}}, "pm") == ""


def test_for_team_lists_each_teammates_skills_with_what_they_do(tmp_path):
    import scranton_skills as sk
    d = tmp_path / "skills" / "animate"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: animate\ndescription: Add motion to a page.\n---\nbody\n")
    cfg = {"team": {"skills": {"limit": True, "dirs": [str(tmp_path / "skills")],
                               "allow": {"motion": ["animate", "choreograph"]}}}}
    out = sk.for_team(cfg)
    got = {s["name"]: s for s in out["motion"]}
    assert got["animate"]["installed"] is True and "motion" in got["animate"]["about"]
    assert got["choreograph"]["installed"] is False


def test_plugins_not_given_to_a_teammate_are_switched_off():
    import scranton_skills as sk
    cfg = {"team": {"skills": {"limit": True, "plugins": {"pm": ["product-management"]}}}}
    ids = ["figma@claude-plugins-official", "product-management@knowledge-work-plugins"]
    assert sk.plugins_off(cfg, "pm", ids) == {"figma@claude-plugins-official": False}
    assert set(sk.plugins_off(cfg, "dev", ids)) == set(ids)
    assert sk.plugins_off({"team": {"skills": {"limit": True}}}, "pm", ids) == {}


def test_chatgpt_models_come_from_the_list_codex_keeps_on_this_mac(tmp_path, monkeypatch):
    import json
    import scranton_team as T
    f = tmp_path / "models_cache.json"
    f.write_text(json.dumps({"models": [
        {"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list", "priority": 6, "description": "Previous generation model for complex coding."},
        {"slug": "gpt-7-nova", "display_name": "GPT-7-Nova", "visibility": "list", "priority": 1, "description": "Newest."},
        {"slug": "gpt-reserve", "display_name": "GPT-Reserve", "visibility": "hide", "priority": 2, "description": "x"},
        {"slug": "bad slug!", "display_name": "x", "visibility": "list", "priority": 3}]}))
    assert T.codex_models(f) == [["gpt-7-nova", "GPT-7 Nova", ""], ["gpt-6-astra", "GPT-6 Astra", "Older"]]
    monkeypatch.setattr(T, "CODEX_CACHE", f)
    assert [m[0] for m in T.models_for("codex")] == ["", "gpt-7-nova", "gpt-6-astra"]
    assert T.models_for("codex", current="gpt-5.5")[-1][0] == "gpt-5.5"            # what a teammate runs on stays selectable
    monkeypatch.setattr(T, "CODEX_CACHE", tmp_path / "missing.json")
    assert any(m[0] == "gpt-6.2-astra" for m in T.models_for("codex"))               # no file: the built-in list
