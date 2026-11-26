"""Scranton: connections (Claude / ChatGPT / Cursor sign-in), per-teammate model,
start / stop / restart, and the data behind a teammate's profile page.

Sign-in always goes through the official CLI's own login (subscription), never an
API key. Per-teammate choices made in the UI are kept in data/teammates.json and
merged by config_loader (only the keys in EDITABLE), so config.toml stays untouched.
"""
from config_loader import PAID_API_ENV
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
from safe_io import atomic_write

ROOT = Path(__file__).parent
OVERRIDES = ROOT / "data" / "teammates.json"
EDITABLE = ("model", "permissions", "autostart", "label", "role", "avatar", "provider", "effort")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# What each app's CLI accepts: `claude --effort` and Codex's model_reasoning_effort.
EFFORTS_BY = {"claude": ("low", "medium", "high", "xhigh", "max"), "codex": ("low", "medium", "high", "xhigh"),
              "gemini": ("low", "medium", "high")}   # agy --effort
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}$")

# Each provider: CLI names, how to sign in, where its login lives, model hints.
PROVIDERS = {
    "claude": {
        "name": "Claude", "plan": "Claude Pro / Max", "commands": ["claude"],
        "login": "claude", "login_hint": "In the window that opens, type /login and follow the browser.",
        # Claude Code takes an alias (always the latest of that tier) or a full model name.
        # Which ones your plan allows is decided by Anthropic; an unavailable one fails at start.
        "models": [
            ["", "Default", "Claude Code picks"],
            # Specific versions, newest first (no "latest" aliases: you see exactly what runs).
            # 11-25: Fable 5.2 (9 Nov 2026, needs Claude Code 2.1.321+) replaces Fable 5.1.
            ["claude-fable-5-2", "Fable 5.2", ""], ["claude-opus-5-5", "Opus 5.5", ""],
            ["claude-sonnet-5-5", "Sonnet 5.5", ""], ["claude-haiku-5-5", "Haiku 5.5", ""],
            ["claude-fable-5-1", "Fable 5.1", "Older"], ["claude-opus-5", "Opus 5", "Older"], ["claude-sonnet-5", "Sonnet 5", "Older"],
            ["claude-opus-4-8", "Opus 4.8", "Older"], ["claude-opus-4-7", "Opus 4.7", "Older"],
            ["claude-opus-4-6", "Opus 4.6", "Older"], ["claude-haiku-4-5", "Haiku 4.5", "Older"],
        ],
    },
    "codex": {
        "name": "ChatGPT (Codex)", "plan": "ChatGPT Plus / Pro", "commands": ["codex"],
        "login": "codex login", "login_hint": "Pick “Sign in with ChatGPT” in the browser.",
        # developers.openai.com/codex/models (ChatGPT sign-in)
        "models": [
            ["", "Default", ""],
            # 11-19: GPT-6 Astra (in Codex since 3 Sep 2026, needs codex-cli 0.153.1+) and the GPT-5.6
            # family; GPT-5.4 left Codex on 31 Aug 2026 and 5.2 / 5.3-codex are deprecated.
            # 11-25: GPT-6.2 Astra and Sol (17 Nov 2026, in the CLI's list from codex-cli 0.171.0):
            # Astra for the hardest work, Sol for everyday coding. They replace GPT-6 Astra and GPT-6.1 Sol.
            ["gpt-6.2-astra", "GPT-6.2 Astra", "Recommended"], ["gpt-6.2-sol", "GPT-6.2 Sol", "Recommended"],
            ["gpt-5.6-terra", "GPT-5.6 Terra", "Everyday"], ["gpt-5.6-luna", "GPT-5.6 Luna", "Everyday"],
            ["gpt-6-astra", "GPT-6 Astra", "Older"], ["gpt-6.1-sol", "GPT-6.1 Sol", "Older"],
            ["gpt-5.6-sol", "GPT-5.6 Sol", "Older"], ["gpt-5.5", "GPT-5.5", "Older"],
        ],
    },
    "cursor": {
        "name": "Cursor", "plan": "Cursor Pro", "commands": ["agent", "cursor-agent"],
        "login": "agent login", "login_hint": "Sign in to Cursor in the browser.",
        "models": [["", "Default", ""]],   # filled from `agent models` on this Mac (see cursor_models)
    },
    # Google's Antigravity CLI (agy), which replaced Gemini CLI. Gemini 4 Argon needs a paid
    # Google AI plan; agy falls back to its own default for a model your plan doesn't have.
    "gemini": {
        "name": "Gemini (Antigravity)", "plan": "Google AI Pro / Ultra", "commands": ["agy"],
        "login": "agy", "login_hint": "In the window that opens, sign in with Google in the browser.",
        # Argon has its own weekly quota; the Flash and Pro models share one pool that refills
        # every few hours. Pictures come from agy's own image tool (Nano Banana), whichever is picked.
        # (third field = the group in the menu)
        "models": [["", "Default", ""],
                   # Neon, Carbon, Hydrogen (11-18, 11-11): ids as the Gemini API names them. Not yet seen
                   # accepted by agy on Lu's plan; check the status line after picking one.
                   ["gemini-4-neon", "Gemini 4 Neon", "Recommended"],
                   ["gemini-4-argon", "Gemini 4 Argon", "Recommended"],
                   ["gemini-4-carbon", "Gemini 4 Carbon", "Recommended"],
                   ["gemini-4-hydrogen", "Gemini 4 Hydrogen", "Recommended"],
                   ["gemini-3.8-flash", "Gemini 3.8 Flash", "Recommended"],
                   ["gemini-3.7-flash", "Gemini 3.7 Flash", "Older"],
                   ["gemini-3.1-pro", "Gemini 3.1 Pro", "Older"]],
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
    if key == "label":
        value = str(value or "").strip()[:40]
        if not value:
            raise ValueError("a name can't be empty")
    if key == "role":
        value = " ".join(str(value or "").split())[:300]
    if key == "provider":
        if value not in COMMANDS:
            raise ValueError("pick Claude, ChatGPT, Cursor or Gemini")
        key, value = "command", COMMANDS[value]
    if key == "effort":
        value = str(value or "")
        allowed = EFFORTS_BY.get(provider_of(config["agents"][name].get("command", "")), ())
        if value and value not in allowed:
            raise ValueError("thinking is " + (", ".join(allowed) or "not adjustable for this app"))
    if key == "avatar":
        value = str(value or "").strip()
        if value and ("/" in value or "\\" in value or not (ROOT / "static" / "avatars" / value).is_file()):
            raise ValueError("pick one of the pictures")
    with _lock:
        data = load_overrides()
        entry = data.setdefault(name, {})
        if key == "command" and entry.get("command", config["agents"][name].get("command")) != value:
            # model names differ per app: forget the old one everywhere it is kept
            for d in (entry, config["agents"][name], data.get("_added", {}).get(name, {})):
                d.pop("model", None)
                d.pop("effort", None)
        if name in data.get("_added", {}):      # agents added in Settings keep everything in one place
            target = data["_added"][name]
            if value in ("", None):
                target.pop(key, None)
            else:
                target[key] = value
        if value in ("", None):
            entry.pop(key, None)
        else:
            entry[key] = value
        if not entry:
            data.pop(name, None)
        OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(OVERRIDES, json.dumps(data, indent=2, ensure_ascii=False))
        # live config sees it too
        config["agents"][name].update({k: v for k, v in entry.items()})
        if key not in entry:
            config["agents"][name].pop(key, None)
    return entry


# ---------------------------------------------------------------- add / delete agents

HANDLE_RE = re.compile(r"^[a-z][a-z0-9-]{1,16}$")   # "dm-" + handle must fit a 20-char channel name
COMMANDS = {"claude": "claude", "codex": "codex", "cursor": "agent", "gemini": "agy"}


def _write(data: dict) -> None:
    OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(OVERRIDES, json.dumps(data, indent=2, ensure_ascii=False))


def project_folders(config: dict) -> list[str]:
    seen = []
    for k in ((config or {}).get("team", {}).get("projects", {}) or {}):
        seen.append(k)
    for a in (config or {}).get("agents", {}).values():
        c = str(a.get("cwd", "") or "")
        home = os.path.expanduser("~")
        if c.startswith(home):
            c = "~" + c[len(home):]
        if c and c not in seen and c != "helper":
            seen.append(c)
    return seen


def add_agent(spec: dict, config: dict) -> dict:
    handle = str(spec.get("handle", "")).strip().lower()
    if not HANDLE_RE.match(handle) or handle.startswith("dm") or handle in ("all", "lu", "system", "user"):
        raise ValueError("the @handle is 2–17 lowercase letters, numbers or dashes, starting with a letter")
    if handle in (config or {}).get("agents", {}):
        raise ValueError(f"@{handle} already exists")
    provider = str(spec.get("provider", "claude"))
    if provider not in COMMANDS:
        raise ValueError("pick Claude, ChatGPT or Cursor")
    label = str(spec.get("label", "")).strip()[:40] or handle
    folder = str(spec.get("cwd", "")).strip()
    if folder not in project_folders(config):
        raise ValueError("pick one of the project folders")
    cfg = {"label": label, "command": COMMANDS[provider], "cwd": folder,
           "role": " ".join(str(spec.get("role", "")).split())[:300], "autostart": True, "added_in_ui": True}
    avatar = str(spec.get("avatar", "") or "")
    if avatar and avatar in avatars():
        cfg["avatar"] = avatar
    model = str(spec.get("model", "") or "").strip()
    if model:
        if not MODEL_RE.match(model):
            raise ValueError("model names are letters, numbers, dots, dashes and colons")
        cfg["model"] = model
    with _lock:
        data = load_overrides()
        data.setdefault("_added", {})[handle] = cfg
        removed = [n for n in data.get("_removed", []) if n != handle]
        data["_removed"] = removed
        _write(data)
    live = dict(cfg)
    live["cwd"] = os.path.expanduser(folder)
    config.setdefault("agents", {})[handle] = live
    return {"handle": handle, **cfg}


def delete_agent(name: str, config: dict, run_dir: Path) -> None:
    if name not in (config or {}).get("agents", {}):
        raise ValueError("unknown agent")
    if name == "help":
        raise ValueError("the Scranton helper can't be deleted (it collects your feedback)")
    stop(name, config, run_dir)
    with _lock:
        data = load_overrides()
        if name in data.get("_added", {}):
            data["_added"].pop(name)
        else:
            data["_removed"] = sorted(set(data.get("_removed", [])) | {name})
        data.pop(name, None)
        _write(data)
    removed = config["agents"].pop(name, None)
    if removed is not None and name not in load_overrides().get("_added", {}):
        config.setdefault("_library", {})[name] = removed   # a built-in role: can come back from the Library


def library(config: dict) -> list[dict]:
    """Built-in roles that aren't on the team right now."""
    out = []
    for name, a in sorted(((config or {}).get("_library") or {}).items()):
        out.append({"handle": name, "label": a.get("label", name), "role": a.get("role", ""),
                    "app": PROVIDERS.get(provider_of(a.get("command", "")), {}).get("name", a.get("command", "")),
                    "avatar": a.get("avatar", "")})
    return out


def restore_agent(name: str, config: dict) -> dict:
    lib = (config or {}).get("_library") or {}
    if name not in lib:
        raise ValueError("that role isn't in the Library")
    with _lock:
        data = load_overrides()
        data["_removed"] = [n for n in data.get("_removed", []) if n != name]
        if not data["_removed"]:
            data.pop("_removed")
        _write(data)
    a = lib.pop(name)
    if isinstance(a.get("cwd"), str):
        a["cwd"] = os.path.expanduser(a["cwd"])
    config.setdefault("agents", {})[name] = a
    return {"handle": name}


# ---------------------------------------------------------------- connections

def provider_of(command: str) -> str:
    c = Path(str(command or "")).name
    if c in ("agent", "cursor-agent"):
        return "cursor"
    if c == "agy":
        return "gemini"
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
        if pid == "gemini":
            # agy keeps its Google sign-in in the macOS keychain (or credentials.enc); we can't read it.
            # Saved conversations only exist once it has been signed in and used.
            d = home / ".gemini" / "antigravity-cli"
            conv = d / "conversations"
            if (d / "credentials.enc").exists() or (conv.is_dir() and any(conv.iterdir())):
                return True, "Google sign-in"
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
            "login_hint": p["login_hint"], "models": models_for(pid) if cli else p["models"],
            "default_model": provider_defaults().get(pid, ""),
        })
    return out


SEEN_MODELS = ROOT / "data" / "models-seen.json"


def _model_ids(pid: str) -> list[list[str]]:
    # The app's own short menu, not every effort and speed of every model: a card saying
    # "New model: Gemini 4 Neon Low, use as default?" for each of 285 variants is noise, and one
    # tap on it changes every teammate on that app (Lu's phone, 11-19).
    # An older model that only now shows up in the list is not news.
    return [[m[0], m[1]] for m in models_for(pid) if m and m[0] and (m[2] if len(m) > 2 else "") != "Older"]


def new_models() -> dict:
    """Models an app offers now that you haven't been told about yet, per app.
    The first time an app is seen, its whole list is recorded silently."""
    try:
        seen = json.loads(SEEN_MODELS.read_text("utf-8"))
    except (OSError, ValueError):
        seen = {}
    out, changed = {}, False
    for pid in PROVIDERS:
        if pid == "cursor" and not any(shutil.which(c) for c in PROVIDERS[pid]["commands"]):
            continue
        cur = _model_ids(pid)
        if pid not in seen:
            seen[pid] = [m[0] for m in cur]
            changed = True
            continue
        fresh = [m for m in cur if m[0] not in set(seen[pid])]
        if fresh:
            out[pid] = {"name": PROVIDERS[pid]["name"], "models": fresh, "default": provider_defaults().get(pid, "")}
    if changed:
        _write_json(SEEN_MODELS, seen)
    return out


def mark_models_seen(pid: str) -> None:
    if pid not in PROVIDERS:
        raise ValueError("unknown app")
    try:
        seen = json.loads(SEEN_MODELS.read_text("utf-8"))
    except (OSError, ValueError):
        seen = {}
    seen[pid] = sorted(set(seen.get(pid, [])) | {m[0] for m in _model_ids(pid)})
    _write_json(SEEN_MODELS, seen)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))


QUIET = ROOT / "data" / "quiet-hours.json"
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def quiet_hours() -> dict:
    try:
        q = json.loads(QUIET.read_text("utf-8"))
    except (OSError, ValueError):
        q = {}
    return {"enabled": bool(q.get("enabled", True)), "from": q.get("from", "22:00"), "to": q.get("to", "08:00")}


def set_quiet_hours(enabled, start: str, end: str) -> dict:
    if not (_TIME_RE.match(str(start)) and _TIME_RE.match(str(end))):
        raise ValueError("times are HH:MM")
    q = {"enabled": bool(enabled), "from": start, "to": end}
    _write_json(QUIET, q)
    return q


def provider_defaults() -> dict:
    d = load_overrides().get("_defaults")
    return d if isinstance(d, dict) else {}


def set_provider_default(pid: str, model: str) -> dict:
    """Model an app's agents use when they don't pick their own ("" = the app's default)."""
    if pid not in PROVIDERS:
        raise ValueError("unknown app")
    model = str(model or "").strip()
    if model and not MODEL_RE.match(model):
        raise ValueError("model names are letters, numbers, dots, dashes and colons")
    data = load_overrides()
    d = data.get("_defaults") if isinstance(data.get("_defaults"), dict) else {}
    if model:
        d[pid] = model
    else:
        d.pop(pid, None)
    data["_defaults"] = d
    _write(data)
    return {"ok": True, "default_model": model}


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
    script = f"unset {' '.join(PAID_API_ENV)}; clear; echo 'Scranton: sign in to {p['name']}'; {cmd}"
    osa = script.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{osa}"',
                      "-e", 'tell application "Terminal" to activate'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "hint": p["login_hint"]}


_cursor_cache = {"at": 0.0, "models": []}


def cursor_models() -> list[list[str]]:
    """The models this Cursor account can use, from `agent models` (cached 10 minutes)."""
    if time.time() - _cursor_cache["at"] < 600:
        return _cursor_cache["models"]
    cli = next((c for c in PROVIDERS["cursor"]["commands"] if shutil.which(c)), "")
    found = []
    if cli:
        for args in (["models"], ["--list-models"]):
            try:
                out = subprocess.run([cli, *args], capture_output=True, text=True, timeout=20,
                                     env={k: v for k, v in os.environ.items() if k != "CURSOR_API_KEY"}).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            for line in out.splitlines():
                line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip(" -*•\t")
                m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._:\-]{1,63})(?:\s+[-–]\s+(.*?))?(?:\s+\((?:current|default)\))*\s*$", line)
                if m and not line.lower().startswith(("available", "loading", "tip", "usage")):
                    found.append([m.group(1), (m.group(2) or m.group(1)).strip(), "Your Cursor plan"])
            if found:
                break
    _cursor_cache.update(at=time.time(), models=found)
    return found


def model_label(pid: str, model: str) -> str:
    """Short name for a teammate's model, for lists ("Opus 5.5"; "Claude" when it's the app's default)."""
    for m in PROVIDERS.get(pid, {}).get("models", []):
        if m and m[0] == (model or "") and model:
            return m[1]
    if model:
        # ids the app lists itself (e.g. Cursor's "cursor-grok-4.6-high"): make them readable
        m = re.sub(r"^cursor-", "", model)
        m = re.sub(r"-(high|medium|low|xhigh|max|none|minimal)(-fast)?$", lambda x: " Fast" if x.group(2) else "", m)
        parts = [p for p in re.split(r"[-_]", m) if p]
        return " ".join(p.upper() if p in ("gpt", "glm") else p.capitalize() if p.isalpha() else p for p in parts) or model
    return PROVIDERS.get(pid, {}).get("name", "").split(" (")[0]


_EFFORT = r"(?:None|Minimal|Low|Medium|High|Extra High|Max)"


def _cursor_plain(label: str) -> str:
    """'Claude Opus 5.5 1M High Fast' -> 'Claude Opus 5.5': the model without its size, effort and speed."""
    t = re.sub(r"[\u200b\u200c\u200d]", "", label or "")
    t = re.sub(r"\(NO ZDR\)|\b1M\b|\bNo Thinking\b|\bThinking\b|\bFast\b", " ", t)
    t = re.sub(rf"\b{_EFFORT}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def cursor_short(models: list[list[str]]) -> list[list[str]]:
    """`agent models` lists every size, effort and speed of every model (285 on Lu's plan, 11-18:
    'Cursor 里面选的话不会出现那么多'). Cursor's own picker shows one line per model, so do the same:
    the newest version of each model, at the effort Cursor itself uses for it."""
    best: dict[str, tuple] = {}          # line ("Claude Opus") -> (version, plain name, id)
    order: list[str] = []
    for mid, label, *_ in models:
        if mid == "auto":
            continue
        plain = _cursor_plain(label)
        nums = re.findall(r"\d+(?:\.\d+)?", plain)
        line = re.sub(r"\s+", " ", re.sub(r"[-\s]?\d+(?:\.\d+)?", " ", plain)).strip()
        ver = tuple(float(n) for n in nums[:1])
        # the variant Cursor shows under the bare name is its own default for that model
        bare = re.sub(r"\s+", " ", re.sub(r"\(NO ZDR\)|\b1M\b|[\u200b\u200c\u200d]", " ", label)).strip() == plain
        # no bare name (Grok 4.7 only comes as Low/Medium/High): medium, the middle of what is offered
        rank = 3 if bare else 2 if re.search(r"-medium$", mid) else 1 if re.search(r"-high$", mid) else 0
        cur = best.get(line)
        if cur is None:
            order.append(line)
        if cur is None or ver > cur[0] or (ver == cur[0] and rank > cur[3]):
            best[line] = (ver, plain, mid, rank)
    out = [["auto", "Auto", "Cursor"]] if any(m[0] == "auto" for m in models) else []
    return out + [[best[k][2], best[k][1], "Cursor"] for k in order]


# What Cursor's own model menu shows (Lu's screenshot, 11-18: "参考它就可以了。再做一个 mode 一般大家
# 也都不会选"): one fixed effort per model, in Cursor's order and under Cursor's two headings.
CURSOR_MENU = [
    ["auto", "Auto", ""],
    ["grok-4.7-low", "Grok 4.7 Low", "Cursor Models"],
    ["cursor-grok-4.6-high-fast", "Grok 4.6 High Fast", "Cursor Models"],
    ["composer-2.5-fast", "Composer 2.5 Fast", "Cursor Models"],
    ["claude-opus-5-5-medium", "Claude Opus 5.5 Medium", "Other Models"],
    ["gemini-4-neon-high", "Gemini 4 Neon High", "Other Models"],
    ["gemini-4-carbon-medium", "Gemini 4 Carbon Medium", "Other Models"],
    ["muse-wonder-1.0-high", "Muse Wonder High", "Other Models"],
    ["gpt-5.6-sol-medium", "GPT-5.6 Sol Medium", "Other Models"],
    ["claude-fable-5-2-high", "Claude Fable 5.2 High", "Other Models"],
    ["claude-sonnet-5-5-high", "Claude Sonnet 5.5 High", "Other Models"],
]


def cursor_menu(models: list[list[str]]) -> list[list[str]]:
    """Cursor's menu, minus anything this account's `agent models` no longer offers. When Cursor
    has moved on so far that most of it is gone, fall back to one line per model."""
    have = {m[0] for m in models}
    menu = [list(m) for m in CURSOR_MENU if m[0] in have]
    return menu if len(menu) >= 5 else cursor_short(models)


CODEX_CACHE = Path.home() / ".codex" / "models_cache.json"


def codex_models(path: Path | None = None) -> list[list[str]]:
    """What ChatGPT (Codex) offers this account right now, from the list the Codex CLI itself keeps
    up to date on this Mac (Lu, 11-25: "不要每次都要我来给它更新"). Newest first, as Codex orders
    them; the ones Codex calls previous generation or legacy go under Older. Empty when the file
    isn't there or can't be read: the built-in list is used then."""
    try:
        data = json.loads((path or CODEX_CACHE).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    rows = []
    for m in (data.get("models") if isinstance(data, dict) else None) or []:
        if not isinstance(m, dict) or m.get("visibility") != "list":
            continue
        slug = str(m.get("slug") or "")
        if not MODEL_RE.match(slug):
            continue
        desc = str(m.get("description") or "")
        old = bool(re.match(r"\s*(previous generation|legacy)\b", desc, re.I))
        name = re.sub(r"^GPT-(\d[\d.]*)-", r"GPT-\1 ", str(m.get("display_name") or slug))   # "GPT-6.2-Astra" -> "GPT-6.2 Astra"
        try:
            pr = int(m.get("priority"))
        except (TypeError, ValueError):
            pr = 999
        rows.append((pr, [slug, name, "Older" if old else ""]))
    return [r for _, r in sorted(rows, key=lambda x: x[0])]


def models_for(pid: str, current: str = "", full: bool = False) -> list[list[str]]:
    base = [list(m) + [""] * (3 - len(m)) for m in PROVIDERS.get(pid, {}).get("models", [["", "Default", ""]])]
    if pid == "codex":
        live = codex_models()
        if live:                                   # Codex's own list wins; ours is only the fallback
            base = [["", "Default", ""]] + live
            if current and current not in {m[0] for m in base}:
                base.append([current, model_label(pid, current), "In use"])
    if pid == "cursor":
        every = cursor_models()
        seen = {m[0] for m in base}
        base += [m for m in (every if full else cursor_menu(every)) if m[0] not in seen]
        if current and current not in {m[0] for m in base}:   # keep what this teammate runs on selectable
            hit = next((m for m in every if m[0] == current), None)
            base.append([current, hit[1] if hit else model_label(pid, current), "In use"])
    return base


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

def avatars() -> list[str]:
    d = ROOT / "static" / "avatars"
    return sorted(p.name for p in d.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                  and p.name != "upload-grok.jpg") if d.is_dir() else []   # Grok Bot's own picture isn't for teammates


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
        "models": models_for(pid, str(a.get("model", "") or "")),
        "permissions": str(a.get("permissions", team.get("permissions", "ask"))),
        "autostart": bool(a.get("autostart", True)),
        "folder": str(a.get("cwd", "")),
        "worktree": bool(a.get("worktree", False)),
        "role_card": card,
        "role_card_text": card_text,
        "channels": sorted(ch for ch, ns in (members or {}).items() if name in ns),
        "recent": recent,
        "avatar": str(a.get("avatar", "") or ""),
        "avatars": avatars(),
        "effort": str(a.get("effort", "") or ""),
        "efforts": list(EFFORTS_BY.get(pid, ())),
    }


def team_permissions(current: str = "ask") -> dict:
    """The team-wide permission level and whether Lu has been asked yet (first launch).
    `current` is what config.toml says, shown until a choice is saved."""
    data = load_overrides()
    team = data.get("_team") or {}
    return {"permissions": team.get("permissions", current if current in ("full", "ask") else "ask"),
            "asked": bool(team.get("asked"))}


def set_team_permissions(level: str) -> dict:
    if level not in ("full", "ask"):
        raise ValueError("permissions is full or ask")
    data = load_overrides()
    data["_team"] = {**(data.get("_team") or {}), "permissions": level, "asked": True}
    _write(data)
    return team_permissions()
