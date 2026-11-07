"""Scranton housekeeping: update check and resuming stopped teammates.

- Update: every few hours `git fetch` the Scranton repo and count commits on
  origin/<branch> that aren't here yet. The UI shows a banner; "Update now"
  pulls (fast-forward only) and restarts the server. Teammates keep running
  in tmux and re-register with the new server by themselves.
- Resume: a teammate whose pid file exists but whose process is gone stopped
  without `./scranton.sh stop` (crash, gave up after repeated exits, Mac slept
  and killed it...). The UI lists them and offers to start them again.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN_DIR = ROOT / "data" / "run"
CHECK_EVERY = 3600  # git fetch once an hour; not the GitHub REST API, so it doesn't touch the bot's rate limit

_state = {"behind": 0, "subject": "", "checked_at": 0.0, "error": "", "updating": False}
_lock = threading.Lock()


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout)


def _branch() -> str:
    r = _git("rev-parse", "--abbrev-ref", "HEAD")
    b = r.stdout.strip()
    return b if r.returncode == 0 and b and b != "HEAD" else "main"


def check_update() -> dict:
    """Fetch and compare with origin. Never raises; errors go into the state."""
    with _lock:
        try:
            if not (ROOT / ".git").exists():
                raise RuntimeError("not a git checkout")
            branch = _branch()
            f = _git("fetch", "--quiet", "origin", branch, timeout=90)
            if f.returncode != 0:
                raise RuntimeError((f.stderr or "git fetch failed").strip().splitlines()[-1][:200])
            c = _git("rev-list", "--count", f"HEAD..origin/{branch}")
            behind = int(c.stdout.strip() or 0)
            subj = ""
            if behind:
                s = _git("log", "-1", "--format=%s", f"origin/{branch}")
                subj = s.stdout.strip()[:160]
            _state.update(behind=behind, subject=subj, error="", checked_at=time.time())
        except Exception as e:  # offline, no repo, no credentials...
            _state.update(error=str(e)[:200], checked_at=time.time())
        return dict(_state)


def status() -> dict:
    st = dict(_state)
    f = RUN_DIR / "update_failed"
    st["failed"] = f.read_text().strip()[:300] if f.exists() else ""
    return st


def _start_checker():
    def loop():
        time.sleep(20)  # let the server come up first
        while True:
            check_update()
            time.sleep(CHECK_EVERY)
    threading.Thread(target=loop, daemon=True, name="scranton-update-check").start()


def apply_update() -> dict:
    """Fast-forward to origin and restart the server. Returns what happened."""
    with _lock:
        if _state["updating"]:
            return {"ok": False, "error": "An update is already running."}
        dirty = _git("status", "--porcelain", "--untracked-files=no")
        if dirty.stdout.strip():
            return {"ok": False, "error": "Scranton has local changes, so it can't update automatically. "
                                          "Run `git status` in the Scranton folder, or ask @help."}
        branch = _branch()
        old_head = _git("rev-parse", "HEAD").stdout.strip()
        p = _git("pull", "--ff-only", "--quiet", "origin", branch, timeout=120)
        if p.returncode != 0:
            return {"ok": False, "error": (p.stderr or "git pull failed").strip().splitlines()[-1][:200]}
        # Dependencies may have changed. If they won't install, go back before restarting.
        py = ROOT / ".venv" / "bin" / "python"
        if py.exists():
            try:
                pip = subprocess.run([str(py), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
                                     capture_output=True, text=True, timeout=300)
                pip_ok, pip_err = pip.returncode == 0, (pip.stderr or "").strip()
            except subprocess.TimeoutExpired:
                pip_ok, pip_err = False, "timed out"
            if not pip_ok:
                if old_head:
                    _git("reset", "--hard", "--quiet", old_head)
                return {"ok": False, "error": "The new version's packages wouldn't install, so nothing changed. "
                                              + (pip_err.splitlines()[-1][:160] if pip_err else "")}
        # scranton.sh restart-server rolls back to this commit if the new server won't start.
        if old_head:
            RUN_DIR.mkdir(parents=True, exist_ok=True)
            (RUN_DIR / "prev_head").write_text(old_head)
        _state.update(behind=0, subject="", updating=True)
    _restart_server_soon()
    return {"ok": True}


def _restart_server_soon():
    """Ask scranton.sh to restart the server from a detached process, after this response is sent."""
    script = ROOT / "scranton.sh"
    cmd = f"sleep 1; '{script}' restart-server >> '{ROOT / 'data' / 'logs' / 'update.log'}' 2>&1"
    subprocess.Popen(["/bin/sh", "-c", cmd], cwd=str(ROOT), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- resume ---------------------------------------------------------------

def _alive(pid: int) -> bool:
    """Running AND one of ours: pid files survive a reboot and macOS reuses low pids."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False  # someone else's process, so not our teammate
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return True  # can't tell; err on "still running" so we never start a duplicate
    return "wrapper.py" in cmd or "run.py" in cmd


def stopped_agents(config: dict) -> list[str]:
    """Teammates with a pid file whose process is gone."""
    names = []
    agents = (config or {}).get("agents", {})
    if not RUN_DIR.is_dir():
        return names
    for f in sorted(RUN_DIR.glob("*.pid")):
        name = f.stem
        if name == "server" or name not in agents:
            continue
        try:
            pid = int(f.read_text().strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if not pid or not _alive(pid):
            names.append(name)
    return names


_resume_lock = threading.Lock()


def resume(names: list[str], config: dict) -> dict:
    """Start teammates that stopped. Only ones that are really stopped right now: a second
    tap (or a second device) must never delete a live pid file and start a duplicate."""
    script = ROOT / "scranton.sh"
    started = []
    with _resume_lock:
        stopped = set(stopped_agents(config))
        for n in names:
            if n not in stopped or not n.replace("-", "").replace("_", "").isalnum():
                continue
            try:
                (RUN_DIR / f"{n}.pid").unlink()  # stale; scranton.sh would think it's still running
            except FileNotFoundError:
                pass
            log = ROOT / "data" / "logs" / "resume.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "ab") as out:
                subprocess.Popen([str(script), "start-agent", n], cwd=str(ROOT), start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
            started.append(n)
    return {"ok": True, "started": started}


def ensure_running(names: list[str], config: dict) -> dict:
    """Start teammates that aren't running (added to a channel, or @-mentioned).
    Returns which ones were started, already running, or can't start and why."""
    import shutil
    agents = (config or {}).get("agents", {})
    script = ROOT / "scranton.sh"
    out = {"started": [], "running": [], "failed": {}}
    with _resume_lock:
        for n in dict.fromkeys(names):
            a = agents.get(n)
            if not isinstance(a, dict) or not n.replace("-", "").replace("_", "").isalnum():
                continue
            pid_file = RUN_DIR / f"{n}.pid"
            try:
                pid = int(pid_file.read_text().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and _alive(pid):
                out["running"].append(n)
                continue
            cmd = str(a.get("command", n))
            if not shutil.which(cmd):
                out["failed"][n] = f"'{cmd}' isn't installed on this Mac"
                continue
            cwd = Path(os.path.expanduser(str(a.get("cwd", "."))))
            known = {os.path.expanduser(k) for k in ((config or {}).get("team", {}).get("projects", {}) or {})}
            if not (cwd if cwd.is_absolute() else ROOT / cwd).is_dir() and str(cwd) not in known:
                out["failed"][n] = f"its folder {a.get('cwd')} doesn't exist"
                continue   # (a known project folder is cloned by scranton.sh start-agent)
            try:
                pid_file.unlink()
            except FileNotFoundError:
                pass
            log = ROOT / "data" / "logs" / "resume.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "ab") as fh:
                subprocess.Popen([str(script), "start-agent", n], cwd=str(ROOT), start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT)
            out["started"].append(n)
    return out


def dismiss(names: list[str]) -> None:
    """'Not now': forget these stale pid files so the prompt doesn't come back."""
    for n in names:
        if n.replace("-", "").replace("_", "").isalnum():
            try:
                (RUN_DIR / f"{n}.pid").unlink()
            except FileNotFoundError:
                pass


def install(app, get_config):
    """Register the routes on the FastAPI app and start the update checker."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.get("/api/scranton/status")
    async def scranton_status():
        cfg = get_config()
        return JSONResponse({"update": status(), "stopped": stopped_agents(cfg)})

    @app.post("/api/scranton/update/check")
    async def scranton_update_check():
        import asyncio
        return JSONResponse(await asyncio.to_thread(check_update))

    @app.post("/api/scranton/update/apply")
    async def scranton_update_apply():
        import asyncio
        return JSONResponse(await asyncio.to_thread(apply_update))

    @app.post("/api/scranton/update/failed/dismiss")
    async def scranton_update_failed_dismiss():
        try:
            (RUN_DIR / "update_failed").unlink()
        except FileNotFoundError:
            pass
        return JSONResponse({"ok": True})

    @app.post("/api/scranton/resume")
    async def scranton_resume(request: Request):
        body = await request.json()
        names = [str(n) for n in (body.get("names") or [])][:30]
        return JSONResponse(resume(names, get_config()))

    @app.post("/api/scranton/resume/dismiss")
    async def scranton_resume_dismiss(request: Request):
        body = await request.json()
        dismiss([str(n) for n in (body.get("names") or [])][:30])
        return JSONResponse({"ok": True})

    if os.environ.get("SCRANTON_NO_UPDATE_CHECK") != "1" and "pytest" not in sys.modules:
        _start_checker()
