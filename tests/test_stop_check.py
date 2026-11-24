"""The check a Claude teammate passes before it can finish a turn (tools/stop_check.py)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import scranton_skills as sk

spec = importlib.util.spec_from_file_location("stop_check", Path(__file__).resolve().parent.parent / "tools" / "stop_check.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)


def _repo(tmp_path):
    r = tmp_path / "site"
    (r / "app").mkdir(parents=True)
    (r / "design-system-foundation.css").write_text(
        ":root{--font-size-body: 0.9375rem;--font-size-caption: 0.8125rem;--font-size-subhead: 1.25rem;--font-size-display: clamp(2rem, 5vw, 4rem);}\n")
    (r / "app" / "card.module.css").write_text(".a{color:red;font-size:14px}\n.a2{font-size:14px}\n.a3{font-size:12px}\n.a4{font-size:12px}\n")
    run = lambda *a: subprocess.run(["git", *a], cwd=r, check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
    return r


def test_a_raw_font_size_is_sent_back_twice_then_let_through(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "ROOT", tmp_path / "scranton")
    r = _repo(tmp_path)
    (r / "app" / "new.module.css").write_text(".x{font-size:1px}\n")
    subprocess.run(["git", "add", "-N", "app/new.module.css"], cwd=r, check=True)
    (r / "app" / "new.module.css").write_text(".b{font-size:14px}\n.c{font-size: 0.8125rem}\n.d{font-size:89px}\n.e{font-size:22.5px}\n")
    code, msg = sc.run("dev", {"cwd": str(r)})
    assert code == 2 and "new.module.css:3" in msg and "font-size 89px is new" in msg and "new.module.css:4" in msg
    assert "new.module.css:1 " not in msg and "new.module.css:2 " not in msg       # 14px is in use, 13px is a token
    assert sc.run("dev", {"cwd": str(r), "stop_hook_active": True}) == (0, "")     # already continuing: no loop
    assert sc.run("dev", {"cwd": str(r)})[0] == 2
    assert sc.run("dev", {"cwd": str(r)}) == (0, "")                               # third time: not a trap
    log = [json.loads(x) for x in (tmp_path / "scranton" / "data" / "stop-check" / "log.jsonl").read_text().splitlines()]
    assert [x["result"] for x in log] == ["sent-back", "sent-back", "let-through"]


def test_tokens_and_a_stated_reason_pass_and_an_unchanged_branch_is_not_rechecked(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "ROOT", tmp_path / "scranton")
    r = _repo(tmp_path)
    (r / "app" / "card.module.css").write_text(
        ".a{color:red;font-size:14px}\n.a2{font-size:14px}\n.a3{font-size:12px}\n.a4{font-size:12px}\n.b{font-size:var(--font-size-body)}\n.c{font-size:13.5px} /* ds-ok: matches the chart label */\n")
    assert sc.run("dev", {"cwd": str(r)}) == (0, "")
    monkeypatch.setattr(sc, "size_findings", lambda *a: (_ for _ in ()).throw(AssertionError("checked again")))
    assert sc.run("dev", {"cwd": str(r)}) == (0, "")
    assert sc.run("dev", {"cwd": str(tmp_path)}) == (0, "")                        # not a repository


def test_a_project_without_a_size_scale_is_left_alone_and_a_crash_never_blocks(tmp_path, monkeypatch):
    r = _repo(tmp_path)
    monkeypatch.setattr(sc, "in_use", lambda *a: {14.0: 5})
    assert sc.size_findings(r, "HEAD", "+++ b/app/a.css\n@@ -0,0 +1 @@\n+.a{font-size:89px}\n", {}) == []
    monkeypatch.setattr(sc, "run", lambda *a: 1 / 0)
    monkeypatch.setattr(sc, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["stop_check.py", "--agent", "dev"])
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))
    assert sc.main() == 0


def test_only_the_named_teammates_get_the_hook_in_their_own_settings_file(tmp_path, monkeypatch):
    cfg = {"team": {"stop_checks": {"agents": ["dev"]}, "skills": {"limit": True, "dirs": [str(tmp_path)], "allow": {"dev": [], "qa": []}}}}
    monkeypatch.setattr(sk, "claude_plugins", lambda *a: [])
    args = sk.launch_args(cfg, "dev", "claude", tmp_path)
    body = json.loads(Path(args[1]).read_text())
    hook = body["hooks"]["Stop"][0]["hooks"][0]
    assert hook["type"] == "command" and "stop_check.py" in hook["command"] and hook["command"].endswith("--agent dev")
    assert "hooks" not in json.loads(Path(sk.launch_args(cfg, "qa", "claude", tmp_path)[1]).read_text())
    assert sk.stop_hook(cfg, "qa") == {}
