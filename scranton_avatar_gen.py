"""Draw a new teammate picture in the team's style, with ChatGPT (Codex CLI, your subscription).

Settings → a teammate's picture → "Generate": `codex exec` gets the role and one or two of the
existing pictures as style references, makes ONE image with its image tool and saves it; macOS
`sips` crops it square and shrinks it to a 256 px JPEG in static/avatars/ (git-ignored, like uploads).

Subscription only: the API-key variables are removed before Codex starts (same as scranton.sh).
Runs in the background; the page polls the job.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
AV = ROOT / "static" / "avatars"
WORK = ROOT / "data" / "avatar-gen"
PAID_API_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX", "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "CURSOR_API_KEY")
TAKEN = ("bear", "fox", "raccoon", "snake", "cat", "lynx", "otter", "rabbit", "ferret", "tortoise",
         "beaver", "squirrel", "hedgehog", "owl")
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _safe(s: str, n: int = 20) -> str:
    return "".join(c for c in s.lower() if c.isalnum() or c == "-")[:n] or "agent"


def start(label: str, role: str, handle: str, like: str) -> dict:
    if not shutil.which("codex"):
        return {"error": "Needs the ChatGPT app (Codex CLI) on this Mac: Settings → Connections"}
    if not shutil.which("sips"):
        return {"error": "Generating pictures works on a Mac only"}
    refs = []
    if like and "/" not in like and (AV / like).is_file():
        refs.append(AV / like)
    for p in sorted(AV.glob("0*.jpg"))[:2]:
        if p not in refs:
            refs.append(p)
    refs = refs[:2]
    jid = uuid.uuid4().hex[:10]
    with _lock:
        if sum(1 for j in _jobs.values() if j["state"] == "working") >= 2:
            return {"error": "Two pictures are already being drawn. Try again in a minute."}
        _jobs[jid] = {"state": "working", "started": time.time()}
    threading.Thread(target=_run, args=(jid, label, role, handle, refs), daemon=True).start()
    return {"id": jid}


def status(jid: str) -> dict:
    with _lock:
        j = dict(_jobs.get(jid) or {"state": "error", "error": "unknown job"})
    return j


def _done(jid: str, **kw):
    with _lock:
        _jobs[jid].update(kw)


def _run(jid: str, label: str, role: str, handle: str, refs: list[Path]):
    out = WORK / jid
    out.mkdir(parents=True, exist_ok=True)
    target = out / "avatar.png"
    prompt = (
        "Make ONE picture with your image generation tool, then save it as the file "
        f"{target} (copy it there from wherever the tool saved it). Make only this one image.\n\n"
        "Style: exactly like the attached reference pictures: a cute, fluffy, 3D plush-toy animal, "
        "front view, head and upper body centred, big glossy dark eyes, rosy cheeks, soft studio light, "
        "plain warm cream background, square framing. No text, letters or logos anywhere.\n"
        f"Animal: pick one that is NOT any of these: {', '.join(TAKEN)}.\n"
        f"It is the team's \"{label}\". What it does: {role or label}. "
        "It wears or holds two or three small props that show that job.\n\n"
        "When the file is saved, reply with just: DONE"
    )
    env = {k: v for k, v in os.environ.items() if k not in PAID_API_ENV}
    cmd = ["codex", "exec", "--skip-git-repo-check", "--full-auto", "-C", str(out)]
    for r in refs:
        cmd += ["-i", str(r)]
    cmd.append(prompt)
    t0 = time.time()
    try:
        subprocess.run(cmd, cwd=str(out), env=env, stdin=subprocess.DEVNULL,
                       stdout=open(out / "codex.log", "wb"), stderr=subprocess.STDOUT, timeout=420)
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:  # noqa: BLE001
        _done(jid, state="error", error=f"Couldn't start ChatGPT: {e}")
        return
    src = target if target.is_file() else _newest_generated(t0)
    if not src:
        _done(jid, state="error", error="ChatGPT didn't make a picture. Details: data/avatar-gen/" + jid + "/codex.log")
        return
    fname = f"upload-gen-{_safe(handle)}-{int(time.time())}.jpg"
    if not _square_jpeg(src, AV / fname):
        _done(jid, state="error", error="Couldn't convert the picture")
        return
    _done(jid, state="done", file=fname)


def _newest_generated(since: float):
    """Codex keeps generated images under ~/.codex/generated_images/<thread>/ even if it didn't copy one."""
    base = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "generated_images"
    best = None
    if base.is_dir():
        for p in base.rglob("*"):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and p.stat().st_mtime >= since:
                if best is None or p.stat().st_mtime > best.stat().st_mtime:
                    best = p
    return best


def _square_jpeg(src: Path, dst: Path) -> bool:
    """Centre-crop to a square, 256 px JPEG, with macOS sips."""
    try:
        info = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(src)],
                              capture_output=True, text=True, timeout=30).stdout
        w = int(info.split("pixelWidth:")[1].split()[0])
        h = int(info.split("pixelHeight:")[1].split()[0])
        side = min(w, h)
        tmp = dst.with_suffix(".tmp.png")
        shutil.copyfile(src, tmp)
        subprocess.run(["sips", "-c", str(side), str(side), str(tmp)], capture_output=True, timeout=30, check=True)
        subprocess.run(["sips", "-Z", "256", "-s", "format", "jpeg", "-s", "formatOptions", "85", str(tmp),
                        "--out", str(dst)], capture_output=True, timeout=30, check=True)
        tmp.unlink(missing_ok=True)
        return dst.is_file()
    except Exception:
        return False
