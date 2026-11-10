"""Backup API keys: when a teammate's Claude or ChatGPT plan hits its limit, it keeps working on
the pay-per-use API until the plan has had time to reset (Lu, 11-10).

- Keys live in data/keys/<provider> (0600, folder 0700; data/ is gitignored). The API never
  returns a key, only that one is set and its last 4 characters.
- A teammate is "on the API" only while listed in data/api-mode.json. Nothing else ever gets the
  key: setting ANTHROPIC_API_KEY for everyone would silently move every Claude teammate onto
  pay-per-use for good.
- The key reaches the CLI through a tiny `sh -c` that reads the file, so it's never on a
  command line (ps) or in tmux's environment.
- After TRY_PLAN_AFTER hours the teammate is restarted on its plan; if the plan is still out,
  it hits the limit again and goes straight back to the API.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import time
from pathlib import Path

ROOT = Path(__file__).parent
KEYS_DIR = ROOT / "data" / "keys"
MODE_FILE = ROOT / "data" / "api-mode.json"
TRY_PLAN_AFTER = 5 * 3600          # Claude's limit window is 5 hours

# Scranton provider -> (key file, env var the CLI reads, what the key looks like, where to cap spend)
PROVIDERS = {
    "claude": ("anthropic", "ANTHROPIC_API_KEY", re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,}$"),
               "https://console.anthropic.com/settings/limits"),
    "codex": ("openai", "OPENAI_API_KEY", re.compile(r"^sk-[A-Za-z0-9_\-]{20,}$"),
              "https://platform.openai.com/settings/organization/limits"),
}


def provider_of_command(command: str) -> str:
    c = Path(str(command or "")).name
    return c if c in PROVIDERS else ""


def _key_path(provider: str) -> Path:
    return KEYS_DIR / PROVIDERS[provider][0]


def get_key(provider: str) -> str:
    if provider not in PROVIDERS:
        return ""
    try:
        return _key_path(provider).read_text("utf-8").strip()
    except OSError:
        return ""


def set_key(provider: str, key: str) -> str:
    """Save (or with an empty key, remove) a provider's backup key. Returns an error or ""."""
    if provider not in PROVIDERS:
        return "unknown app"
    key = (key or "").strip()
    path = _key_path(provider)
    if not key:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return ""
    if not PROVIDERS[provider][2].match(key):
        return ("That doesn't look like an Anthropic API key (starts with sk-ant-)." if provider == "claude"
                else "That doesn't look like an OpenAI API key (starts with sk-).")
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(KEYS_DIR, 0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return ""


def summary() -> dict:
    out = {}
    for p, (_f, _e, _rx, limits) in PROVIDERS.items():
        k = get_key(p)
        out[p] = {"set": bool(k), "last4": k[-4:] if k else "", "limits_url": limits}
    return out


# ---------------------------------------------------------------- who is on the API right now
def _load_mode() -> dict:
    try:
        data = json.loads(MODE_FILE.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_mode(data: dict) -> None:
    MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), "utf-8")
    os.replace(tmp, MODE_FILE)


def on_api(name: str) -> dict | None:
    return _load_mode().get(name)


def all_on_api() -> dict:
    return _load_mode()


def start_api(name: str, provider: str) -> bool:
    """Mark a teammate as on the API. False when there's no key for its app."""
    if not get_key(provider):
        return False
    data = _load_mode()
    data[name] = {"provider": provider, "since": time.time()}
    _save_mode(data)
    return True


def end_api(name: str) -> bool:
    data = _load_mode()
    if name not in data:
        return False
    data.pop(name)
    _save_mode(data)
    return True


def due_back(now: float | None = None) -> list[str]:
    now = now or time.time()
    return [n for n, v in _load_mode().items() if now - float(v.get("since") or 0) >= TRY_PLAN_AFTER]


# ---------------------------------------------------------------- launching on the API
def wrap_command(name: str, base_name: str, command_line: str) -> str:
    """The agent's command line, run so the key is read from its file at start (not passed on
    the command line). Unchanged unless this teammate is on the API right now."""
    st = on_api(name) or on_api(base_name)
    if not st:
        return command_line
    provider = st.get("provider", "")
    if provider not in PROVIDERS or not get_key(provider):
        return command_line
    env = PROVIDERS[provider][1]
    path = str(_key_path(provider))
    script = f'{env}="$(cat {shlex.quote(path)})"; export {env}; exec "$0" "$@"'
    return f"sh -c {shlex.quote(script)} {command_line}"


def approve_for_claude(home: Path | None = None) -> None:
    """Claude Code asks once, in its terminal, before an ANTHROPIC_API_KEY overrides the
    subscription. Record the approval (its last 20 characters) the way Claude Code itself does."""
    key = get_key("claude")
    if not key:
        return
    path = (home or Path.home()) / ".claude.json"
    try:
        data = json.loads(path.read_text("utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return   # unreadable: leave it; the question then shows up in chat
    if not isinstance(data, dict):
        return
    resp = data.get("customApiKeyResponses")
    if not isinstance(resp, dict):
        resp = {}
    approved = [x for x in resp.get("approved", []) if isinstance(x, str)]
    rejected = [x for x in resp.get("rejected", []) if isinstance(x, str) and x != key[-20:]]
    if key[-20:] in approved and len(rejected) == len(resp.get("rejected", [])):
        return
    if key[-20:] not in approved:
        approved.append(key[-20:])
    resp.update({"approved": approved, "rejected": rejected})
    data["customApiKeyResponses"] = resp
    tmp = path.with_name(path.name + ".scranton-tmp")
    tmp.write_text(json.dumps(data, indent=2), "utf-8")
    os.replace(tmp, path)
