"""Close a project: hand-over note, chat saved to a file, old files set aside, channel removed.

Lu, 2026-11-19: "我不可能一个项目一直做下去，那之后交接、关 channel 这个怎么做？… 除了 push，
local file 也需要清理，就留最终版本。"

Everything a closed project leaves behind is in one folder, ~/.scranton/ARCHIVE/<channel>/:
  HANDOFF.md      written by the project manager: where the final version is, what was decided,
                  what is not done, where to start next time
  cleanup.txt     written by the project manager: one path per line, old versions and working
                  files that are no longer needed
  chat.md         the whole channel, readable; chat.jsonl the same as data
  _to_delete/     where the files from cleanup.txt are MOVED. Nothing is deleted: the owner
                  empties this folder herself after a look.

The parts here are the ones that must not depend on a teammate getting it right: which paths may
be moved, the export, the move.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

ARCHIVE = "~/.scranton/ARCHIVE"
KEEP_NAMES = {"HANDOFF.md", "cleanup.txt", "chat.md", "chat.jsonl"}


def archive_dir(channel: str, base: str = ARCHIVE) -> Path:
    safe = "".join(c for c in channel if c.isalnum() or c in "-_") or "channel"
    return Path(os.path.expanduser(base)) / safe


def start_text(channel: str, folder: Path, owner: str) -> str:
    """What the project manager is asked to do when the owner presses Close project."""
    return (
        f"@pm {owner} 要关闭这个项目。先别派新活，按顺序做完这四件事，做完在这里回一句「交接写好了」：\n"
        f"1. 写交接文档 {folder}/HANDOFF.md：最终版在哪（路径、链接、PR），定过的事（带消息号），没做完的事，下次接手先做什么。只写事实，一页以内。\n"
        f"2. 所有改动推到 GitHub（各人自己的分支），HANDOFF.md 里写上分支和 PR。\n"
        f"3. 写清理清单 {folder}/cleanup.txt：一行一个绝对路径，只列这个项目的旧版本、中间稿、重复文件（各人 OUTBOX 和 worktree 里的）。"
        f"最终版、原稿、{owner} 给的参考不要列。拿不准的不要列。\n"
        f"4. 看板上还开着的行：做完的改成已上线，不做的在备注里写一句为什么。\n"
        f"清单里的文件不会被删，只会移到 {folder}/_to_delete/，由 {owner} 自己看过再清空。你和队友都不要自己删文件。"
    )


def export_chat(msgs: list[dict], folder: Path, label=lambda s: s) -> tuple[Path, int]:
    """Write the channel as chat.md (readable) and chat.jsonl (as stored). Returns (chat.md, count)."""
    folder.mkdir(parents=True, exist_ok=True)
    lines, day = [], ""
    for m in msgs:
        ts = float(m.get("timestamp") or 0)
        d = time.strftime("%Y-%m-%d", time.localtime(ts))
        if d != day:
            day = d
            lines.append(f"\n## {d}\n")
        who = label(str(m.get("sender") or ""))
        head = f"**{who}** {time.strftime('%H:%M', time.localtime(ts))} (#{m.get('id')})"
        if m.get("reply_to") is not None:
            head += f" ↳ #{m.get('reply_to')}"
        lines.append(head)
        text = str(m.get("text") or "").rstrip()
        if text:
            lines.append(text)
        for a in m.get("attachments") or []:
            if isinstance(a, dict):
                lines.append(f"[file: {a.get('name') or 'file'}] {a.get('url') or ''}".rstrip())
        lines.append("")
    md = folder / "chat.md"
    md.write_text(f"# {folder.name}\n" + "\n".join(lines), "utf-8")
    with open(folder / "chat.jsonl", "w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return md, len(msgs)


def read_cleanup(folder: Path, roots: list[Path]) -> dict:
    """The project manager's cleanup.txt, checked. A path is moved only when it exists, sits inside
    a folder the team works in, is not such a folder itself, and is not part of a git repository's
    own data or the archive. Everything else is refused, with the reason shown to the owner."""
    f = folder / "cleanup.txt"
    ok, refused = [], []
    if not f.is_file():
        return {"exists": False, "ok": ok, "refused": refused, "bytes": 0}
    seen = set()
    for raw in f.read_text("utf-8", errors="replace").splitlines():
        line = raw.strip().lstrip("-*• ").strip().strip("`\"'")
        if not line or line.startswith("#"):
            continue
        try:
            p = Path(os.path.expanduser(line))
            if not p.is_absolute():
                refused.append({"path": line, "why": "not an absolute path"})
                continue
            link = p.is_symlink()
            rp = p.resolve()
        except (OSError, RuntimeError):
            refused.append({"path": line, "why": "not a path"})
            continue
        if link:
            refused.append({"path": line, "why": "a link to somewhere else"})
            continue
        if str(rp) in seen:
            continue
        seen.add(str(rp))
        root = next((r for r in roots if r in rp.parents), None)
        why = ""
        if not rp.exists():
            why = "not found"
        elif root is None:
            why = "outside the folders the team works in" if rp not in roots else "a whole working folder"
        elif ".git" in rp.relative_to(root).parts:
            why = "inside a git repository's own data"
        elif len(rp.relative_to(root).parts) == 1 and rp.is_dir() and (rp / ".git").exists():
            why = "a whole repository or worktree"
        elif rp.name in KEEP_NAMES or folder.resolve() in rp.parents or rp == folder.resolve():
            why = "part of the hand-over"
        if why:
            refused.append({"path": line, "why": why})
        else:
            ok.append(str(rp))
    size = 0
    for s in ok:
        p = Path(s)
        try:
            size += sum(x.stat().st_size for x in p.rglob("*") if x.is_file()) if p.is_dir() else p.stat().st_size
        except OSError:
            pass
    return {"exists": True, "ok": ok, "refused": refused, "bytes": size}


def move_aside(paths: list[str], folder: Path) -> dict:
    """Move each path into <archive>/_to_delete/, keeping its full path underneath so nothing
    collides and everything can be put back by hand."""
    dest = folder / "_to_delete"
    moved, failed = [], []
    for s in paths:
        src = Path(s)
        to = dest / str(src).lstrip("/")
        try:
            to.parent.mkdir(parents=True, exist_ok=True)
            if to.exists():
                to = to.with_name(f"{to.name}.{int(time.time())}")
            shutil.move(str(src), str(to))
            moved.append(s)
        except (OSError, shutil.Error) as e:
            failed.append({"path": s, "why": str(e)[:120]})
    return {"moved": moved, "failed": failed, "dest": str(dest)}
