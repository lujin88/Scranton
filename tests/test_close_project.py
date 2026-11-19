import json
from pathlib import Path

import scranton_close as sc


def test_chat_is_saved_readable_and_as_data(tmp_path):
    msgs = [{"id": 1, "sender": "Lu", "text": "做首页", "timestamp": 1795000000, "channel": "p"},
            {"id": 2, "sender": "pm", "text": "好", "timestamp": 1795000100, "channel": "p", "reply_to": 1,
             "attachments": [{"name": "a.png", "url": "/uploads/a.png"}]}]
    md, n = sc.export_chat(msgs, tmp_path / "p", lambda s: {"pm": "项目经理"}.get(s, s))
    text = md.read_text("utf-8")
    assert n == 2 and "**项目经理**" in text and "↳ #1" in text and "[file: a.png] /uploads/a.png" in text and "做首页" in text
    assert [json.loads(l)["id"] for l in (tmp_path / "p" / "chat.jsonl").read_text("utf-8").splitlines()] == [1, 2]


def test_only_safe_paths_are_set_aside_and_nothing_is_deleted(tmp_path):
    root = tmp_path / "work"
    wt = root / "dev"
    (wt / ".git").mkdir(parents=True)
    (wt / "OUTBOX" / "v1").mkdir(parents=True)
    (wt / "OUTBOX" / "v1" / "a.png").write_text("x" * 2048)
    (wt / "OUTBOX" / "final.png").write_text("f")
    (tmp_path / "private.txt").write_text("secret")
    (wt / "link").symlink_to(tmp_path / "private.txt")
    folder = tmp_path / "ARCHIVE" / "p"
    folder.mkdir(parents=True)
    (folder / "HANDOFF.md").write_text("x")
    (folder / "cleanup.txt").write_text("\n".join([
        f"- {wt}/OUTBOX/v1", f"{wt}/OUTBOX/v1",            # the same thing twice
        f"{tmp_path}/private.txt", f"{wt}/.git", f"{wt}", f"{root}", "relative/file.png",
        f"{wt}/missing.png", f"{wt}/link", f"{folder}/HANDOFF.md", "# a note", ""]))
    got = sc.read_cleanup(folder, [root.resolve(), (tmp_path / "ARCHIVE").resolve()])
    assert got["ok"] == [str((wt / "OUTBOX" / "v1").resolve())] and got["bytes"] == 2048
    why = {Path(r["path"]).name: r["why"] for r in got["refused"]}
    assert "outside" in why["private.txt"] and "git" in why[".git"] and "whole" in why["dev"] and "whole" in why["work"]
    assert why["file.png"] == "not an absolute path" and why["missing.png"] == "not found" and "link" in why["link"]
    assert why["HANDOFF.md"] == "part of the hand-over"
    out = sc.move_aside(got["ok"], folder)
    assert out["moved"] and not out["failed"] and not (wt / "OUTBOX" / "v1").exists()
    assert (folder / "_to_delete" / str((wt / "OUTBOX" / "v1").resolve()).lstrip("/") / "a.png").read_text() == "x" * 2048
    assert (wt / "OUTBOX" / "final.png").exists() and (tmp_path / "private.txt").exists()
    assert sc.read_cleanup(tmp_path / "nothing", [root])["exists"] is False
