"""Scranton: connections (Claude / ChatGPT / Cursor sign-in), per-teammate model,
start / stop / restart, and the data behind a teammate's profile page.

Sign-in always goes through the official CLI's own login (subscription), never an
API key. Per-teammate choices made in the UI are kept in data/teammates.json and
merged by config_loader (only the keys in EDITABLE), so config.toml stays untouched.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
OVERRIDES = ROOT / "data" / "teammates.json"
EDITABLE = ("model", "permissions", "autostart")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}$")

# Each provider: CLI names, how to sign in, where its login lives, model hints.
PROVIDERS = {
    "claude": {
        "name": "Claude", "plan": "Claude Pro / Max", "commands": ["claude"],
        "login": "claude", "login_hint": "In the window that opens, type /login and follow the browser.",
        # Claude Code's own aliases, always valid
        "models": [["", "Default"], ["opus", "Opus"], ["sonnet", "Sonnet"], ["haiku", "Haiku"]],
    },
    "codex": {
        "name": "ChatGPT (Codex)", "plan": "ChatGPT Plus / Pro", "commands": ["codex"],
        "login": "codex login", "login_hint": "Pick “Sign in with ChatGPT” in the browser.",
        "models": [["", "Default"]],   # any model name Codex accepts can be typed in
    },
    "cursor": {
        "name": "Cursor", "plan": "Cursor Pro", "commands": ["agent", "cursor-agent"],
        "login": "agent login", "login_hint": "Sign in to Cursor in the browser.",
        "models": [["", "Default"]],
    },
}

_lock = threading.Lock()


# ---------------------------------------------------------------- overrides

def load_overrides() -> dict:
    try:
        data = json.loads(OVERRIDES.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def set_override(name: str, key: str, value, config: dict) -> dict:
    if key not in EDITABLE or name not in (config or {}).get("agents", {}):
        raise ValueError("can't change that")
    if key == "model":
        value = str(value or "").strip()
        if value and not MODEL_RE.match(value):
            raise ValueError("model names are letters, numbers, dots, dashes and colons")
    if key == "permissions" and value not in ("full", "ask"):
        raise ValueError("permissions is full or ask")
    if key == "autostart":
        value = bool(value)
    with _lock:
        data = load_overrides()
        entry = data.setdefault(name, {})
        if value in ("", None):
            entry.pop(key, None)
        else:
            entry[key] = value
        if not entry:
            data.pop(name, None)
        OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
        tmp = OVERRIDES.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        os.replace(tmp, OVERRIDES)
        # live config sees it too
        config["agents"][name].update({k: v for k, v in entry.items()})
        if key not in entry:
            config["agents"][name].pop(key, None)
    return entry


# ---------------------------------------------------------------- connections

def provider_of(command: str) -> str:
    c = Path(str(command or "")).name
    if c in ("agent", "cursor-agent"):
        return "cursor"
    return c if c in PROVIDERS else ""


def _logged_in(pid: str, home: Path) -> tuple[bool | None, str]:
    """Best effort, without running the CLI. None = can't tell."""
    try:
        if pid == "claude":
            st = json.loads((home / ".claude.json").read_text("utf-8"))
            acct = st.get("oauthAccount") or {}
            if acct:
                return True, str(acct.get("emailAddress") or acct.get("displayName") or "")
            return False, ""
        if pid == "codex":
            auth = json.loads((home / ".codex" / "auth.json").read_text("utf-8"))
            if auth.get("tokens"):
                return True, "ChatGPT sign-in"
            if auth.get("OPENAI_API_KEY"):
                return False, "set up with an API key, not your ChatGPT plan"
            return False, ""
        if pid == "cursor":
            for f in (home / ".cursor" / "cli-config.json", home / ".config" / "cursor" / "auth.json"):
                if f.exists():
                    data = json.loads(f.read_text("utf-8") or "{}")
                    info = data.get("authInfo") or data.get("auth") or {}
                    if info:
                        return True, str(info.get("email") or "")
            return None, ""
    except FileNotFoundError:
        return False, ""
    except (OSError, ValueError):
        return None, ""
    return None, ""


def connections(config: dict) -> list[dict]:
    home = Path.home()
    used = {}
    for n, a in (config or {}).get("agents", {}).items():
        p = provider_of(a.get("command", ""))
        if p:
            used.setdefault(p, []).append(n)
    out = []
    for pid, p in PROVIDERS.items():
        cli = next((c for c in p["commands"] if shutil.which(c)), "")
        ok, who = _logged_in(pid, home) if cli else (False, "")
        out.append({
            "id": pid, "name": p["name"], "plan": p["plan"], "installed": bool(cli),
            "connected": ok, "account": who, "teammates": used.get(pid, []),
            "login_hint": p["login_hint"], "models": p["models"],
        })
    return out


def open_login(pid: str) -> dict:
    """Open a Terminal window on this Mac running the CLI's own sign-in."""
    p = PROVIDERS.get(pid)
    if not p:
        return {"ok": False, "error": "unknown"}
    cli = next((c for c in p["commands"] if shutil.which(c)), "")
    if not cli:
        return {"ok": False, "error": f"{p['name']} isn't installed on this Mac yet (see README → Install)."}
    cmd = p["login"].replace(p["commands"][0], cli, 1) if p["commands"][0] != cli else p["login"]
    if sys.platform != "darwin":
        return {"ok": False, "error": f"Run `{cmd}` in a terminal on the Mac."}
    # Strip API keys so the CLI signs in with your plan.
    script = f"unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN OPENAI_API_KEY CURSOR_API_KEY; clear; echo 'Scranton: sign in to {p['name']}'; {cmd}"
    osa = script.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{osa}"',
                      "-e", 'tell application "Terminal" to activate'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "hint": p["login_hint"]}


# ---------------------------------------------------------------- start / stop

def stop(name: str, config: dict, run_dir: Path) -> bool:
    if name not in (config or {}).get("agents", {}):
        return False
    pid_file = run_dir / f"{name}.pid"
    try:
        pid = int(pid_file.read_text().strip() or 0)
    except (OSError, ValueError):
        pid = 0
    import scranton_ops
    if pid and scranton_ops._alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):
            if not scranton_ops._alive(pid):
                break
            time.sleep(0.2)
    subprocess.run(["tmux", "kill-session", "-t", f"=agentchattr-{name}"], capture_output=True)
    try:
        pid_file.unlink()
    except FileNotFoundError:
        pass
    return True


# ---------------------------------------------------------------- profile

def profile(name: str, config: dict, members: dict, recent: list[dict]) -> dict | None:
    a = (config or {}).get("agents", {}).get(name)
    if not isinstance(a, dict):
        return None
    pid = provider_of(a.get("command", ""))
    card = str(a.get("role_card", "") or "")
    card_text = ""
    if card:
        path = (ROOT / card).resolve()
        if str(path).startswith(str(ROOT.resolve())) and path.is_file():
            card_text = path.read_text("utf-8", errors="replace")[:40000]
    team = (config or {}).get("team", {})
    return {
        "handle": name,
        "label": str(a.get("label", name)),
        "role": str(a.get("role", "") or ""),
        "provider": pid,
        "provider_name": PROVIDERS.get(pid, {}).get("name", a.get("command", "")),
        "model": str(a.get("model", "") or ""),
        "models": PROVIDERS.get(pid, {}).get("models", [["", "Default"]]),
        "permissions": str(a.get("permissions", team.get("permissions", "ask"))),
        "autostart": bool(a.get("autostart", True)),
        "folder": str(a.get("cwd", "")),
        "worktree": bool(a.get("worktree", False)),
        "role_card": card,
        "role_card_text": card_text,
        "channels": sorted(ch for ch, ns in (members or {}).items() if name in ns),
        "recent": recent,
    }
