import json, os, time
from pathlib import Path
import scranton_context as sc
import wrapper

ON = {"enabled": True, "hours": 4, "wakes": 40, "context_k": 100}


def test_due_by_context_size():
    now = time.time()
    assert wrapper._handover_due(ON, now, 1, 120_000) is True
    assert wrapper._handover_due(ON, now, 1, 80_000) is False
    assert wrapper._handover_due(ON, now, 1, None) is False            # unknown size: hours/messages only
    assert wrapper._handover_due({**ON, "context_k": 0}, now, 1, 500_000) is False
    assert wrapper._handover_due({**ON, "enabled": False}, now, 99, 500_000) is False
    assert wrapper._handover_due(ON, now, 40, None) is True


def _codex_log(home, cwd, ctx, sub=False):
    d = home / ".codex" / "sessions" / time.strftime("%Y/%m/%d")
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"rollout-{time.time_ns()}.jsonl"
    meta = {"type": "session_meta", "payload": {"cwd": str(cwd), "source": {"subagent": {}} if sub else "cli"}}
    tc = {"type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": ctx}}}}
    f.write_text(json.dumps(meta) + "\n" + json.dumps(tc) + "\n")
    return f


def test_codex_reads_own_session_not_subagent(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    wt = tmp_path / "wt" / "visualqa"; wt.mkdir(parents=True)
    _codex_log(tmp_path, wt, 140_000)
    time.sleep(0.01)
    _codex_log(tmp_path, wt, 5_000, sub=True)          # newer, but a subagent's
    _codex_log(tmp_path, tmp_path / "other", 9_999)     # another teammate
    assert sc.current_context("codex", str(wt), time.time() - 60, home=tmp_path) == 140_000


def test_claude_reads_last_main_usage(tmp_path):
    cwd = "/Users/lu/LuJin-Portfolio-worktrees/dev"
    d = tmp_path / ".claude" / "projects" / "-Users-lu-LuJin-Portfolio-worktrees-dev"
    d.mkdir(parents=True)
    lines = [{"type": "assistant", "message": {"usage": {"input_tokens": 3, "cache_read_input_tokens": 90_000, "cache_creation_input_tokens": 2_000}}},
             {"type": "assistant", "isSidechain": True, "message": {"usage": {"input_tokens": 1}}}]
    (d / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert sc.current_context("claude", cwd, time.time() - 60, home=tmp_path) == 92_003
    assert sc.current_context("agy", cwd, 0, home=tmp_path) is None
