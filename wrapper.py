"""Agent wrapper - runs the real interactive CLI with auto-trigger on @mentions.

Usage:
    python wrapper.py claude
    python wrapper.py codex
    python wrapper.py gemini
    python wrapper.py kimi
    python wrapper.py qwen

Cross-platform:
  - Windows: injects keystrokes via Win32 WriteConsoleInput (wrapper_windows.py)
  - Mac/Linux: injects keystrokes via tmux send-keys (wrapper_unix.py)

How it works:
  1. Starts the agent CLI in an interactive terminal.
  2. Watches the queue file in the background for @mentions from the chat room.
  3. When triggered, injects "use mcp to read #channel - you're mentioned, take appropriate action and respond".
  4. The agent picks up the prompt as if the user typed it.
"""

import json
import re as _re_sub
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent

SERVER_NAME = "agentchattr"


# ---------------------------------------------------------------------------
# Per-instance provider config
# ---------------------------------------------------------------------------

def _restrict(path: Path) -> None:
    """Token files: owner read/write only (0600); our own provider-config dir 0700.
    Hygiene against other OS users and backups that copy permissions. It does NOT
    stop an agent running as the same user from reading them."""
    try:
        os.chmod(path, 0o600)
        if path.parent.name == "provider-config":
            os.chmod(path.parent, 0o700)
    except OSError:
        pass


def _drop_our_server(config_file: Path) -> None:
    """Remove Scranton's entry from a shared MCP config (an older version wrote it there with one
    teammate's token); everything else in the file stays as it is."""
    try:
        data = json.loads(config_file.read_text("utf-8"))
    except (OSError, ValueError):
        return
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if isinstance(servers, dict) and SERVER_NAME in servers:
        servers.pop(SERVER_NAME)
        try:
            config_file.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        except OSError:
            pass


def _write_json_mcp_settings(config_file: Path, url: str, transport: str = "http",
                              *, token: str = "", http_key: str = "httpUrl", server_name: str = "") -> Path:
    """Write/merge a settings-style JSON file with nested mcpServers config.

    Preserves existing servers in the file — only updates the agentchattr entry.

    Gemini CLI 0.32+ expects:
      - "httpUrl" key (not "url") for streamable-http transport
      - "url" key for SSE transport
      - "trust": true to skip per-call approval prompts

    `http_key` controls which JSON key names the HTTP transport URL. Defaults
    to "httpUrl" (Gemini/Qwen). Providers like CodeBuddy that follow the
    standard MCP shape should set `mcp_http_key = "url"` in their config.
    Only affects settings_file / env injector modes (not the Claude flag
    writer or Kilo env_content writer).
    """
    config_file.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if config_file.exists():
        try:
            existing = json.loads(config_file.read_text("utf-8"))
        except Exception:
            pass
    servers = existing.get("mcpServers", {})
    # Default: Gemini-style "httpUrl" for HTTP. Override with http_key="url"
    # for providers that follow the standard MCP shape (e.g. CodeBuddy).
    if transport in ("http", "streamable-http"):
        entry: dict = {"type": "http", http_key: url, "trust": True}
    else:
        entry = {"type": transport, "url": url, "trust": True}
    if token:
        entry["headers"] = {"Authorization": f"Bearer {token}"}
    servers[server_name or SERVER_NAME] = entry
    existing["mcpServers"] = servers

    # Enable folder trust so ~/.gemini/trustedFolders.json is respected
    security = existing.get("security", {})
    folder_trust = security.get("folderTrust", {})
    folder_trust["enabled"] = True
    security["folderTrust"] = folder_trust
    existing["security"] = security

    config_file.write_text(json.dumps(existing, indent=2) + "\n", "utf-8")
    _restrict(config_file)
    return config_file


def _read_project_mcp_servers(project_dir: Path) -> dict:
    """Read existing MCP servers from the project's .mcp.json."""
    mcp_file = project_dir / ".mcp.json"
    if mcp_file.exists():
        try:
            data = json.loads(mcp_file.read_text("utf-8"))
            servers = data.get("mcpServers", {})
            # Remove agentchattr — we'll add our own authenticated version
            servers.pop(SERVER_NAME, None)
            return servers
        except Exception:
            pass
    return {}


def _write_claude_mcp_config(
    config_file: Path,
    url: str,
    *,
    token: str = "",
    project_servers: dict | None = None,
) -> Path:
    """Write a Claude Code --mcp-config file with bearer auth.

    Includes all project MCP servers (unity-mcp etc.) so --strict-mcp-config
    can be used without losing other servers."""
    config_file.parent.mkdir(parents=True, exist_ok=True)

    # Start with other project servers (e.g. unity-mcp)
    servers = dict(project_servers or {})

    # Add agentchattr with bearer token for direct server auth
    entry: dict = {"type": "http", "url": url}
    if token:
        entry["headers"] = {"Authorization": f"Bearer {token}"}
    servers[SERVER_NAME] = entry

    payload = {"mcpServers": servers}
    config_file.write_text(json.dumps(payload, indent=2) + "\n", "utf-8")
    _restrict(config_file)
    return config_file


# ---------------------------------------------------------------------------
# Built-in provider defaults (applied when agent config has no mcp_inject)
# ---------------------------------------------------------------------------

_BUILTIN_DEFAULTS: dict[str, dict] = {
    "claude": {
        "mcp_inject": "flag",
        "mcp_flag": "--mcp-config",
        "mcp_transport": "http",
        "mcp_merge_project": True,  # include unity-mcp etc.
    },
    "gemini": {
        "mcp_inject": "env",
        "mcp_env_var": "GEMINI_CLI_SYSTEM_SETTINGS_PATH",
        "mcp_transport": "http",  # streamable-http; SSE has blocking issues in Gemini 0.32.x
        "mcp_merge_project": True,
    },
    "codex": {
        "mcp_inject": "proxy_flag",
        "mcp_proxy_flag_template": '-c mcp_servers.{server}.url="{url}"',
        # mcp_merge_project disabled — Codex reads .mcp.json natively,
        # and duplicate detection is name-based only (e.g. unityMCP vs unity-mcp)
    },
    # Antigravity CLI (agy) only reads ~/.gemini/config/mcp_config.json (a workspace .agents/ file
    # is ignored: tested on Lu's Mac, 11-10). One shared file, so each teammate gets its own entry
    # ("scranton-<name>", its own token); the server refuses a call made under another
    # teammate's name, so two Gemini teammates can't post as each other.
    "agy": {
        "mcp_inject": "settings_file",
        "mcp_settings_path": "~/.gemini/config/mcp_config.json",
        "mcp_http_key": "serverUrl",
        "mcp_transport": "http",
        "mcp_server_per_instance": True,
    },
    "kimi": {
        "mcp_inject": "flag",
        "mcp_flag": "--mcp-config-file",
        "mcp_transport": "http",
        "mcp_merge_project": True,
    },
    "kilo": {
        "mcp_inject": "env_content",
        "mcp_env_var": "KILO_CONFIG_CONTENT",
        "mcp_transport": "http",
    },
}

_VALID_INJECT_MODES = {"settings_file", "env", "flag", "proxy_flag", "env_content"}


def _provider_from_command(command: object) -> str:
    """Return a built-in provider for an exact configured executable name.

    Named agent identities (for example ``claude2``) are independent of
    the CLI they launch.  Resolve only exact known executable basenames; do
    not guess from prefixes or arbitrary command text.
    """
    if not isinstance(command, str):
        return ""
    executable = command.strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if executable.endswith(suffix):
            executable = executable[:-len(suffix)]
            break
    return executable if executable in _BUILTIN_DEFAULTS else ""


def _resolve_mcp_inject(agent: str, agent_cfg: dict) -> dict:
    """Resolve MCP injection config: explicit config > provider defaults > none."""
    if agent_cfg.get("mcp_inject"):
        return dict(agent_cfg)
    provider = agent
    if provider not in _BUILTIN_DEFAULTS:
        provider = _provider_from_command(agent_cfg.get("command", ""))
    if provider:
        merged = dict(_BUILTIN_DEFAULTS[provider])
        merged.update({k: v for k, v in agent_cfg.items() if k.startswith("mcp_")})
        return merged
    return {}


def _get_server_url(mcp_cfg: dict, transport: str) -> str:
    """Build the MCP server URL for the given transport."""
    if transport == "sse":
        port = mcp_cfg.get("sse_port", 8201)
        return f"http://127.0.0.1:{port}/sse"
    port = mcp_cfg.get("http_port", 8200)
    return f"http://127.0.0.1:{port}/mcp"


def _apply_mcp_inject(
    inject_cfg: dict,
    instance_name: str,
    data_dir: Path,
    proxy_url: str | None,
    *,
    token: str = "",
    mcp_cfg: dict | None = None,
    project_dir: Path | None = None,
) -> tuple[list[str], dict[str, str], Path | None]:
    """Apply MCP config injection based on the resolved inject config.

    Returns (extra_launch_args, inject_env, settings_path_or_None).
    settings_path is stored so re-registration can rewrite it.
    """
    mode = inject_cfg.get("mcp_inject")
    if not mode:
        return [], {}, None

    launch_args: list[str] = []
    inject_env: dict[str, str] = {}
    settings_path: Path | None = None
    config_dir = data_dir / "provider-config"
    transport = inject_cfg.get("mcp_transport", "http")
    server_url = _get_server_url(mcp_cfg or {}, transport)

    http_key = inject_cfg.get("mcp_http_key", "httpUrl")

    if mode == "settings_file":
        # Write a settings JSON file at a user-specified path (e.g. .qwen/settings.json,
        # or ~/.codebuddy/.mcp.json for user-scope configs).
        raw_path = inject_cfg.get("mcp_settings_path", "")
        if not raw_path:
            raise ValueError(f"mcp_inject = 'settings_file' requires mcp_settings_path")
        # Expand ~ to user home (e.g. ~/.codebuddy/.mcp.json), then resolve
        # relative paths against project_dir/CWD as before.
        target = Path(raw_path).expanduser()
        if not target.is_absolute():
            base = Path(project_dir) if project_dir else Path.cwd()
            target = base / target
        per_instance = bool(inject_cfg.get("mcp_server_per_instance"))
        if per_instance:
            _drop_our_server(target)   # the old shared "agentchattr" entry (one teammate's token)
        settings_path = _write_json_mcp_settings(target, server_url,
                                                  transport=transport, token=token,
                                                  http_key=http_key, server_name=f"scranton-{instance_name}" if per_instance else "")
        # Optionally set an env var pointing to the settings file
        env_var = inject_cfg.get("mcp_env_var")
        if env_var:
            inject_env[env_var] = str(settings_path)

    elif mode == "env":
        # Write a settings file in provider-config dir, expose via env var
        env_var = inject_cfg.get("mcp_env_var")
        if not env_var:
            raise ValueError(f"mcp_inject = 'env' requires mcp_env_var")
        settings_path = _write_json_mcp_settings(
            config_dir / f"{instance_name}-settings.json",
            server_url, transport=transport, token=token, http_key=http_key,
        )
        # Merge project .mcp.json servers into the settings file
        merge_project = inject_cfg.get("mcp_merge_project", False)
        if merge_project and project_dir and settings_path:
            project_servers = _read_project_mcp_servers(project_dir)
            if project_servers:
                try:
                    data = json.loads(settings_path.read_text("utf-8"))
                    servers = data.get("mcpServers", {})
                    for name, cfg in project_servers.items():
                        if name not in servers:
                            # Normalize url key for providers that expect "httpUrl"
                            # (Gemini/Qwen). For standard-MCP providers with
                            # http_key="url", leave existing "url" entries as-is.
                            entry = dict(cfg)
                            srv_type = entry.get("type", "http")
                            if srv_type in ("http", "streamable-http") and http_key != "url":
                                if "url" in entry and http_key not in entry:
                                    entry[http_key] = entry.pop("url")
                            entry.setdefault("trust", True)
                            servers[name] = entry
                    data["mcpServers"] = servers
                    settings_path.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
                    _restrict(settings_path)
                except Exception:
                    pass
        inject_env[env_var] = str(settings_path)

    elif mode == "flag":
        # Write a config file, pass it as a CLI flag
        flag = inject_cfg.get("mcp_flag", "--mcp-config")
        merge_project = inject_cfg.get("mcp_merge_project", False)
        project_servers = _read_project_mcp_servers(project_dir) if (merge_project and project_dir) else {}
        settings_path = _write_claude_mcp_config(
            config_dir / f"{instance_name}-mcp.json",
            server_url, token=token, project_servers=project_servers,
        )
        launch_args = [flag, str(settings_path)]

    elif mode == "env_content":
        # Build JSON config content and set it as an env var directly (no file written).
        # Used by Kilo CLI which reads KILO_CONFIG_CONTENT at startup.
        env_var = inject_cfg.get("mcp_env_var")
        if not env_var:
            raise ValueError("mcp_inject = 'env_content' requires mcp_env_var")
        entry: dict = {"type": "remote", "url": server_url, "enabled": True}
        if token:
            entry["headers"] = {"Authorization": f"Bearer {token}"}
        payload = {"mcp": {SERVER_NAME: entry}}
        inject_env[env_var] = json.dumps(payload)

    elif mode == "proxy_flag":
        # Pass the proxy URL as CLI flags (e.g. codex -c ...)
        template = inject_cfg.get("mcp_proxy_flag_template",
                                  '-c mcp_servers.{server}.url="{url}"')
        expanded = template.format(server=SERVER_NAME, url=proxy_url or "")
        launch_args = expanded.split()

    return launch_args, inject_env, settings_path


def _ensure_gemini_folder_trusted(project_dir: Path) -> None:
    """Add project_dir as TRUST_FOLDER in ~/.gemini/trustedFolders.json.

    Gemini CLI blocks ALL MCPs (including system-settings ones) for untrusted
    folders. A more-specific TRUST_FOLDER entry overrides any parent-level
    DO_NOT_TRUST rule, so we always write the exact cwd we're launching in.
    Respects GEMINI_CLI_TRUSTED_FOLDERS_PATH env override if set.
    """
    trusted_path_env = os.environ.get("GEMINI_CLI_TRUSTED_FOLDERS_PATH", "")
    if trusted_path_env:
        trusted_file = Path(trusted_path_env)
    else:
        trusted_file = Path.home() / ".gemini" / "trustedFolders.json"

    try:
        data: dict = {}
        if trusted_file.exists():
            try:
                data = json.loads(trusted_file.read_text("utf-8"))
            except Exception:
                data = {}

        folder_key = str(project_dir)
        if data.get(folder_key) == "TRUST_FOLDER":
            return  # already trusted — nothing to do

        data[folder_key] = "TRUST_FOLDER"
        trusted_file.parent.mkdir(parents=True, exist_ok=True)
        trusted_file.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        print(f"  Trusted folder for Gemini MCPs: {folder_key}")
    except Exception as exc:
        print(f"  Warning: could not update Gemini trusted folders: {exc}")


def _build_provider_launch(
    agent: str,
    agent_cfg: dict,
    instance_name: str,
    data_dir: Path,
    proxy_url: str | None,
    extra_args: list[str],
    env: dict[str, str],
    *,
    token: str = "",
    mcp_cfg: dict | None = None,
    project_dir: Path | None = None,
) -> tuple[list[str], dict[str, str], dict[str, str], Path | None]:
    """Return provider-specific launch args/env/inject_env/settings_path.

    inject_env: env vars that must propagate INTO the agent process.  On
    Mac/Linux these are prefixed onto the tmux command via ``env VAR=val``
    because subprocess.run(env=...) only affects the tmux client binary.
    On Windows they are simply merged into the Popen env dict.
    """
    inject_cfg = _resolve_mcp_inject(agent, agent_cfg)
    mcp_args, inject_env, settings_path = _apply_mcp_inject(
        inject_cfg, instance_name, data_dir, proxy_url,
        token=token, mcp_cfg=mcp_cfg, project_dir=project_dir,
    )

    launch_args = [*mcp_args, *extra_args]
    launch_env = dict(env)

    return launch_args, launch_env, inject_env, settings_path


def _register_instance(server_port: int, base: str, label: str | None = None) -> dict:
    import urllib.request

    reg_body = json.dumps({"base": base, "label": label}).encode()
    reg_req = urllib.request.Request(
        f"http://127.0.0.1:{server_port}/api/register",
        method="POST",
        data=reg_body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(reg_req, timeout=5) as reg_resp:
        return json.loads(reg_resp.read())


def _auth_headers(token: str, *, include_json: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if include_json:
        headers["Content-Type"] = "application/json"
    return headers


# ---------------------------------------------------------------------------
# Queue watcher
# ---------------------------------------------------------------------------

def _notify_recovery(data_dir: Path, agent_name: str):
    """Write a flag file that the server picks up and broadcasts as a system message."""
    try:
        flag = data_dir / f"{agent_name}_recovered"
        flag.write_text(agent_name, "utf-8")
    except Exception:
        pass


_IDENTITY_HINT = (
    " (If this is a multi-instance session, reclaim your previous identity from "
    "your context window, NOT from the chat history before responding. If you "
    "didn't have one, tell the user to give you a name by clicking your status "
    "pill at the top.)"
)


def _fetch_role(server_port: int, agent_name: str) -> str:
    """Fetch this agent's role from the server status endpoint."""
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{server_port}/api/roles")
        with urllib.request.urlopen(req, timeout=3) as resp:
            roles = json.loads(resp.read())
        return roles.get(agent_name, "")
    except Exception:
        return ""


def _fetch_active_rules(server_port: int, token: str = "") -> dict | None:
    """Fetch active rules from the server."""
    try:
        import urllib.request
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        req = urllib.request.Request(f"http://127.0.0.1:{server_port}/api/rules/active", headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _report_rule_sync(server_port: int, agent_name: str, epoch: int, token: str = ""):
    """Report that this agent has seen rules at the given epoch."""
    try:
        import urllib.request
        body = json.dumps({"epoch": epoch}).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"http://127.0.0.1:{server_port}/api/rules/agent_sync/{agent_name}",
            method="POST",
            data=body,
            headers=headers,
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def _quiet_note(now=None) -> str:
    """During Lu's quiet hours (Settings → Profile), ask agents not to @Lu unless it's urgent."""
    try:
        q = json.loads((ROOT / "data" / "quiet-hours.json").read_text("utf-8"))
    except (OSError, ValueError):
        q = {}
    if not q.get("enabled", True):
        return ""
    start, end = str(q.get("from", "22:00")), str(q.get("to", "08:00"))
    import datetime as _dt
    t = (now or _dt.datetime.now()).strftime("%H:%M")
    inside = (start <= t < end) if start <= end else (t >= start or t < end)
    if not inside:
        return ""
    return (f" QUIET HOURS ({start}-{end}, Lu's time): keep working, but don't @Lu now unless it is high-risk "
            f"or something is broken for real users; collect questions for her and post them after {end}.")


def _work_file(queue_file: Path, name: str) -> Path:
    return queue_file.parent / "run" / f"{name}.work.json"


def _remember_work(queue_file: Path, name: str, places, thread_root, channel) -> None:
    """Note what the agent was last asked, so after a restart it can carry on by itself."""
    try:
        ch, th = (places[-1] if places else (channel, thread_root))
        f = _work_file(queue_file, name)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"channel": ch, "thread": th, "at": time.time()}), "utf-8")
    except Exception:
        pass


# Posts the wrapper makes by itself. They aren't the agent answering the request.
_NUDGE = ("Scranton: you worked on the last request in #{ch} but no reply from you reached the chat. "
          "Post your reply now with chat_send, or say what's blocking you.")
_ASKED = [None]   # () -> the question on the agent's screen, set in main() on macOS/Linux
AUTO_POSTS = ("I stopped", "I can't read this yet", "I hit an error", "I'm picking up")


def _replied_since(msgs, name: str, at: float) -> bool:
    base = name.split("-")[0]
    return any(isinstance(m, dict) and float(m.get("timestamp") or 0) > at
               and str(m.get("sender", "")).split("-")[0] == base
               and not str(m.get("text", "")).startswith(AUTO_POSTS)
               for m in msgs)


def _read_channel(server_port: int, token: str, channel: str) -> list:
    import urllib.parse, urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{server_port}/api/messages?channel={urllib.parse.quote(channel)}&limit=200",
        headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def _resume_unfinished(queue_file: Path, name: str, server_port: int, get_token_fn, delay: float = 25.0) -> None:
    """After a restart (Mac rebooted, agent restarted): if the last request wasn't answered,
    ask the agent to pick it up again, without Lu having to @ it."""
    time.sleep(delay)   # let the CLI start and draw its prompt first
    f = _work_file(queue_file, name)
    try:
        w = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return
    at = float(w.get("at") or 0)
    if time.time() - at > 24 * 3600:
        return
    ch, th = str(w.get("channel") or "general"), w.get("thread")
    try:
        msgs = _read_channel(server_port, get_token_fn(), ch)
    except Exception:
        return
    if _replied_since(msgs, name, at):
        return
    where = f"#{ch}" + (f", in the thread under message #{th} (reply with reply_to={th})" if th is not None else "")
    prompt = (f"Scranton was restarted while you were working (for example the Mac restarted), so your earlier session "
              f"ended. Use mcp to read {where}: find the last request to you that you haven't answered, check your "
              f"branch and files for what you already did, and carry on from there. First post one line saying "
              f"where you're picking up.")
    line = {"channel": ch, "prompt": prompt}
    if th is not None:
        line["thread"] = th
    try:
        with open(queue_file, "a", encoding="utf-8") as q:
            q.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass


_OWNER_DEFAULT = ["the owner"]


def _owner_name(queue_file: Path) -> str:
    """The name Lu uses in the chat now (Settings → Profile), so @mentions reach her Activity."""
    try:
        name = json.loads((queue_file.parent / "settings.json").read_text("utf-8")).get("username", "")
        if name and name != "user":
            return str(name)
    except (OSError, ValueError, AttributeError):
        pass
    return _OWNER_DEFAULT[0]


# problem key -> when it was last said in the chat (shared by the queue watcher and the monitor)
_PROBLEM_POSTED: dict = {}

# Where the agent was last asked something, so problems are reported there.
_LAST_PLACE = {"channel": "general", "thread": None}


def _requeue(queue_file: Path, lines: list[str]) -> None:
    """Put undelivered mentions back. Appending (never rewriting) can't erase a
    mention the server adds at the same moment; order inside one batch doesn't matter."""
    try:
        with open(queue_file, "a", encoding="utf-8") as f:
            f.write("".join(l if l.endswith("\n") else l + "\n" for l in lines if l.strip()))
    except OSError:
        pass


def _post(server_port: int, sender: str, token: str, channel: str, reply_to, text: str) -> None:
    """Say something in the chat as this agent (used when a mention can't be delivered)."""
    try:
        import urllib.request
        body = {"text": text, "channel": channel, "sender": sender}
        if reply_to is not None:
            body["reply_to"] = reply_to
        req = urllib.request.Request(
            f"http://127.0.0.1:{server_port}/api/send", method="POST", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
        urllib.request.urlopen(req, timeout=3)
    except Exception as exc:
        print(f"  couldn't post to chat: {exc}", flush=True)


_LIMIT_DETAIL = [""]    # model, quota, % used and reset time for the stop message
_LIMIT_API_OK = [False]   # the last limit check said the plan is really out (numbers, not screen text)


def _ask_limit_check(server_port: int, token: str, place: dict, problem: str) -> str:
    """'ignore' (the plan has room, or we couldn't ask: look again later), 'switched' (another
    model) or 'report'. Never 'report' on a failed check (11-11 09:07–09:12: pm and qa posted
    "I stopped" at 79% of the week while still working)."""
    _LIMIT_API_OK[0] = False
    _LIMIT_DETAIL[0] = ""
    try:
        import urllib.request
        from wrapper_unix import pane_text
        screen = pane_text(_HANDOVER.get("tmux") or "", 40) if _HANDOVER.get("tmux") else ""
        req = urllib.request.Request(
            f"http://127.0.0.1:{server_port}/api/scranton/limit-check", method="POST",
            data=json.dumps({"problem": problem, "text": screen[-3000:], "channel": place.get("channel"),
                             "thread": place.get("thread")}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            got = json.loads(r.read() or b"{}")
            _LIMIT_API_OK[0] = bool(got.get("api_ok"))
            _LIMIT_DETAIL[0] = str(got.get("detail") or "")
            return str(got.get("action") or "ignore")
    except Exception:
        return "ignore"


def _ask_api_fallback(server_port: int, token: str, place: dict) -> bool:
    """True when Scranton is moving this teammate onto its backup API key."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{server_port}/api/scranton/api-fallback", method="POST",
            data=json.dumps({"channel": place.get("channel") or "general", "thread": place.get("thread")}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return bool(json.loads(r.read() or b"{}").get("switching"))
    except Exception:
        return False


def _take_queue(queue_file: Path, taking: Path, keep: int | None = None) -> int:
    """Move what's in the queue into .taking (after anything left there by a stop mid-delivery).
    With keep, only the newest `keep` items stay. Returns how many were dropped."""
    lines = []
    if taking.exists():
        lines += [l for l in taking.read_text("utf-8").splitlines() if l.strip()]
    if queue_file.exists():
        fresh = queue_file.with_name(queue_file.name + ".fresh")
        os.replace(queue_file, fresh)
        lines += [l for l in fresh.read_text("utf-8").splitlines() if l.strip()]
    else:
        fresh = None
    dropped = 0
    if keep is not None and len(lines) > keep:
        dropped, lines = len(lines) - keep, lines[-keep:]
    from safe_io import atomic_write
    atomic_write(taking, "".join(l + "\n" for l in lines))
    if fresh is not None:
        fresh.unlink(missing_ok=True)
    return dropped


# Scranton: fresh-session handover (Settings → Agents → Fresh sessions). Filled in by main().
_HANDOVER = {"command": "", "handoff_dir": None, "busy": None, "cache": None, "at": 0.0}
STUCK_TELL = 30   # minutes "working" with an unchanged screen before saying so
STUCK_ESC = 60    # ... before pressing Esc


def _stuck_signature(screen: str) -> str:
    """The screen with digits and spinner glyphs removed: timers and spinners aren't progress."""
    import re as _r
    lines = [l for l in (screen or "").splitlines() if l.strip()]
    text = "\n".join(lines[-15:])
    text = _r.sub(r"[0-9]", "", text)
    return _r.sub(r"[✻✽✶✳✢·⏺●◐◓◑◒⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏*]", "", text)
_HANDOFF_ASK = ("Scranton: before your next message, save a handoff for a fresh session with the chat_handoff "
                "tool: what you're working on, decisions made and why, open items and who is waiting on what, "
                "the next step, and files / branches / PRs. Plain, under 40 lines. Don't post in the chat; "
                "just call chat_handoff and stop.")


def _handover_settings(server_port: int, token: str) -> dict | None:
    """The handover setting from the server, re-read at most once a minute."""
    if _HANDOVER["cache"] is not None and time.time() - _HANDOVER["at"] < 60:
        return _HANDOVER["cache"]
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{server_port}/api/scranton/handover",
                                     headers={"Authorization": f"Bearer {token}"} if token else {})
        with urllib.request.urlopen(req, timeout=3) as resp:
            _HANDOVER["cache"] = json.loads(resp.read())
    except Exception:
        _HANDOVER["cache"] = None
    _HANDOVER["at"] = time.time()
    return _HANDOVER["cache"]


def _handover_due(settings: dict | None, started: float, wakes: int, context: int | None = None) -> bool:
    if not settings or not settings.get("enabled"):
        return False
    # Context size (Lu, 11-10): every call re-sends the whole session, so a big one is what costs.
    # Only for apps whose log we can read (Claude Code, Codex); None means unknown → hours/messages.
    k = int(settings.get("context_k", 0) or 0)
    if k and context and context >= k * 1000:
        return True
    return (time.time() - started >= float(settings.get("hours", 4)) * 3600
            or wakes >= int(settings.get("wakes", 40)))


def _session_context(started: float) -> int | None:
    """Tokens the teammate's current session sends per call, from its CLI's own log."""
    try:
        import scranton_context
        return scranton_context.current_context(_HANDOVER.get("command") or "", _HANDOVER.get("cwd") or "",
                                                started - 120)
    except Exception:
        return None


def _do_handover(inject_fn, agent_name: str, wait: float = 240.0) -> str | None:
    """Ask for a handoff note, wait for it, start a fresh CLI session. Returns the note, or None
    when anything didn't happen (then the old session simply carries on)."""
    folder = _HANDOVER.get("handoff_dir")
    if not folder:
        return None
    path = Path(folder) / f"{re.sub(r'-[0-9]+$', '', agent_name.lower())}.md"
    before = path.stat().st_mtime if path.exists() else 0.0
    r = inject_fn(_HANDOFF_ASK)
    if r is False or r == "question":
        return None
    deadline = time.time() + wait
    while time.time() < deadline:
        if path.exists() and path.stat().st_mtime > before:
            break
        time.sleep(2)
    else:
        return None
    busy = _HANDOVER.get("busy")
    end = time.time() + 60
    time.sleep(3)
    while busy and busy() and time.time() < end:   # let it finish its turn
        time.sleep(2)
    cmd = os.path.basename(str(_HANDOVER.get("command") or "")).lower()
    r = inject_fn("/new" if cmd.startswith("codex") else "/clear")
    if r is False or r == "question":
        return None
    time.sleep(5)
    try:
        return " ".join(path.read_text("utf-8").split())[:3000]
    except OSError:
        return None


def _queue_watcher(get_identity_fn, inject_fn, *, is_multi_instance: bool = False, trigger_flag=None,
                   server_port: int = 8300, agent_name: str = "", get_token_fn=None,
                   refresh_interval: int = 10, default_role: str = "", team_brief: str = ""):
    """Poll queue file and inject an MCP read task when triggered.

    Scranton: default_role comes from the agent's `role` in config.toml and is
    used when no role was set in the UI. team_brief comes from [team].brief and
    is added on the first wake-up and then every `refresh_interval` wake-ups.
    """
    first_mention = True
    stuck_since = 0.0
    failures = 0
    brief_count = 0
    last_rules_epoch = 0  # 0 = unknown/cold start — will inject on first trigger
    trigger_count = 0
    session_started = time.time()   # Scranton: for the fresh-session handover
    wakes = 0
    ctx_retry_at = 0.0
    while True:
        try:
            _, queue_file = get_identity_fn()
            taking = queue_file.with_name(queue_file.name + ".taking")
            if (queue_file.exists() and queue_file.stat().st_size > 0) or taking.exists():
                # Take the queue in one step (rename), so a mention the server appends meanwhile
                # lands in a fresh file. The taken lines stay in .taking until they've been
                # delivered or put back: a stop in between doesn't lose them.
                _take_queue(queue_file, taking)
                with open(taking, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                has_trigger = False
                channel = "general"
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    has_trigger = True
                    if isinstance(data, dict) and "channel" in data:
                        channel = data["channel"]

                if has_trigger:
                    # Signal activity BEFORE injecting — covers the thinking phase
                    if trigger_flag is not None:
                        trigger_flag[0] = True
                    time.sleep(0.5)

                    # Check if this is a job/activity-scoped trigger
                    job_id = None
                    custom_prompt = ""
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if isinstance(data, dict) and "job_id" in data:
                                job_id = data["job_id"]
                            if isinstance(data, dict):
                                raw_prompt = data.get("prompt", "")
                                if isinstance(raw_prompt, str) and raw_prompt.strip():
                                    custom_prompt = raw_prompt.strip()
                        except json.JSONDecodeError:
                            pass

                    # Scranton: one batch can hold mentions from several places; name each one.
                    places = []   # (channel, thread) in arrival order
                    for line in lines:
                        try:
                            d = json.loads(line)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            continue
                        if not isinstance(d, dict):
                            continue
                        try:
                            th = int(d["thread"]) if d.get("thread") is not None else None
                        except (TypeError, ValueError):
                            th = None
                        key = (str(d.get("channel") or channel), th)
                        if key not in places:
                            places.append(key)
                    thread_root = places[-1][1] if places else None
                    if places:
                        _LAST_PLACE["channel"], _LAST_PLACE["thread"] = places[-1]
                    if custom_prompt:
                        prompt = custom_prompt
                    elif job_id:
                        prompt = f"use mcp to read job_id={job_id} - you're mentioned in a job thread, take appropriate action and respond"
                    elif len(places) > 1:
                        where = "; ".join(f"#{c} in the thread under message #{t} (reply with reply_to={t})" if t is not None
                                          else f"#{c}" for c, t in places)
                        prompt = (f"use mcp to read each of these - you're mentioned in: {where}. "
                                  f"Take appropriate action and reply in each place, where the mention was")
                    elif thread_root is not None:
                        # Scranton: keep the conversation in its thread
                        prompt = (f"use mcp to read #{places[0][0]} - you're mentioned in the thread under message "
                                  f"#{thread_root}; take appropriate action and reply in that thread "
                                  f"(chat_send with reply_to={thread_root})")
                    else:
                        prompt = f"use mcp to read #{places[0][0] if places else channel} - you're mentioned, take appropriate action and respond"

                    # Scranton: a long session gets a fresh one first (handoff note → /clear → note
                    # at the top of this message). Only when the agent isn't in the middle of something.
                    handoff_prefix = ""
                    _htok = get_token_fn() if get_token_fn else ""
                    hs = _handover_settings(server_port, _htok)
                    ctx = _session_context(session_started) if (hs or {}).get("enabled") and time.time() >= ctx_retry_at else None
                    if _handover_due(hs, session_started, wakes, ctx):
                        busy = _HANDOVER.get("busy")
                        if not (busy and busy()):
                            note = _do_handover(inject_fn, agent_name)
                            if note is not None:
                                session_started, wakes = time.time(), 0
                                brief_count, last_rules_epoch, trigger_count, first_mention = 0, 0, 0, True
                                handoff_prefix = ("You're in a fresh session (Scranton starts one now and then to keep "
                                                  f"your context small). Your handoff from before: {note} --- The new message: ")
                            else:
                                # didn't work this time: try again after a while, not on every message
                                wakes = max(0, int(hs.get("wakes", 40)) // 2)
                                session_started = time.time() - float(hs.get("hours", 4)) * 1800
                                ctx_retry_at = time.time() + 20 * 60   # a big context: don't retry on every message

                    # Use current identity (may have changed via rename)
                    current_name, _ = get_identity_fn()
                    _undo = (brief_count, last_rules_epoch, first_mention)
                    # Append role if set — check both current name and base name
                    role = _fetch_role(server_port, current_name)
                    if not role and current_name != agent_name:
                        role = _fetch_role(server_port, agent_name)
                    # UI role (popover) adds to the configured role/card, never hides it.
                    if role and default_role:
                        role = f"{role} | {default_role}"
                    elif not role:
                        role = default_role
                    if role:
                        prompt += f"\n\nROLE: {role}"
                    if team_brief:
                        if brief_count == 0 or (refresh_interval > 0 and brief_count % refresh_interval == 0):
                            prompt += f"\n\nTEAM: {team_brief.replace('{owner}', _owner_name(queue_file))}"
                        brief_count += 1

                    # Smart rules injection: first trigger, epoch change, or periodic refresh
                    _token = get_token_fn() if get_token_fn else ""
                    rules_data = _fetch_active_rules(server_port, _token)
                    trigger_count += 1
                    if rules_data:
                        # Use server-side refresh_interval (live from settings UI)
                        ri = rules_data.get("refresh_interval", refresh_interval)
                        need_inject = (
                            last_rules_epoch == 0
                            or rules_data["epoch"] != last_rules_epoch
                            or (ri > 0 and trigger_count % ri == 0)
                        )
                        if need_inject:
                            if rules_data["rules"]:
                                rules_text = "; ".join(rules_data["rules"])
                                prompt += f"\n\nRULES:\n{rules_text}"
                            last_rules_epoch = rules_data["epoch"]
                            _report_rule_sync(server_port, current_name, rules_data["epoch"], _token)

                    if first_mention and is_multi_instance:
                        prompt += _IDENTITY_HINT
                        first_mention = False
                    # Flatten to single line — multi-line text triggers paste
                    # detection in CLIs (Claude Code shows "[Pasted text +N]")
                    # which can break injection of long session prompts
                    prompt += _quiet_note()
                    prompt = handoff_prefix + prompt
                    result = inject_fn(prompt.replace("\r", " ").replace("\n", " "))
                    blocked = result == "question"
                    if not blocked and result is not False:
                        stuck_since = 0.0
                        failures = 0
                        wakes += 1
                        _remember_work(queue_file, agent_name, places, thread_root, channel)
                    else:
                        # Not delivered: put the mention back and try again shortly.
                        failures += 1
                        # it wasn't delivered, so the brief/rules weren't either
                        brief_count, last_rules_epoch, first_mention = _undo
                        _requeue(queue_file, lines)
                        if trigger_flag is not None:
                            trigger_flag[0] = False
                        if blocked and not stuck_since:
                            stuck_since = time.time()
                            asked = ""
                            try:
                                asked = _ASKED[0]() if _ASKED[0] else ""
                            except Exception:
                                asked = ""
                            _post(server_port, current_name, _token, channel, thread_root,
                                  "I can't read this yet: my terminal is waiting on a question"
                                  + (f": “{asked}”" if asked else "") + ". "
                                  "Open my terminal to answer it, and I'll pick this up right after.")
                            _PROBLEM_POSTED["question"] = time.time()
                        if not blocked and failures == 3:
                            _post(server_port, current_name, _token, channel, thread_root,
                                  "Your message didn't reach me after 3 tries. "
                                  "Restart me: Settings → Agents → me → Restart.")
                        time.sleep(10 if blocked else 3)
                taking.unlink(missing_ok=True)   # delivered, or put back in the queue
        except Exception as exc:
            print(f"  queue watcher: {type(exc).__name__}: {exc}", flush=True)
            try:
                taking.unlink(missing_ok=True)   # a bad batch mustn't repeat forever
            except Exception:
                pass

        time.sleep(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _subagent_args(agent_cfg: dict, command) -> list[str]:
    """Sub-agents for this teammate only (Lu, 11-10: cheaper models for bulk read-only work).
    `subagents` in its config block points at files in roles/subagents/:
    a .json for Claude Code (passed as --agents), .toml files for Codex (one custom agent each,
    passed as -c agents.<name>.* so nothing is written to ~/.codex or the project)."""
    files = agent_cfg.get("subagents") or []
    if isinstance(files, str):
        files = [files]
    provider = _provider_from_command(command)
    out: list[str] = []
    for rel in files:
        path = (ROOT / str(rel)).resolve()
        if not path.is_file() or ROOT.resolve() not in path.parents:
            continue
        try:
            if provider == "claude" and path.suffix == ".json":
                data = json.loads(path.read_text("utf-8"))
                if isinstance(data, dict) and data:
                    out += ["--agents", json.dumps(data, ensure_ascii=False)]
            elif provider == "codex" and path.suffix == ".toml":
                import tomllib
                d = tomllib.loads(path.read_text("utf-8"))
                name = str(d.get("name") or "")
                if _re_sub.fullmatch(r"[a-z][a-z0-9_]{0,40}", name) and d.get("description"):
                    out += ["-c", f"agents.{name}.description={json.dumps(str(d['description']), ensure_ascii=False)}",
                            "-c", f"agents.{name}.config_file={json.dumps(str(path))}"]
        except (OSError, ValueError):
            continue
    return out

# Codex's "Approaching rate limits · switch model?" stops the teammate until someone picks an answer,
# and Scranton read it as "usage limit reached" (visualqa, 11-10). Same as picking "Keep current model
# (never show again)", for Scranton's Codex teammates only: nothing is written to ~/.codex. The real
# "Usage limit reached" still shows.
_CODEX_ARGS = ["-c", "notice.hide_rate_limit_model_nudge=true"]


def main():
    # Scranton: Stop/Restart send SIGTERM; exit through `finally` so we deregister cleanly.
    import signal as _signal
    _signal.signal(_signal.SIGTERM, lambda *_: sys.exit(0))
    import argparse
    import urllib.error
    import urllib.request

    from config_loader import apply_cli_overrides, load_config

    # Apply AGENTCHATTR_* overrides (from CLI flags or env) BEFORE loading
    # config so the wrapper connects to the same data_dir/ports as a server
    # launched with matching flags.
    apply_cli_overrides()
    config = load_config(ROOT)

    agent_names = list(config.get("agents", {}).keys())

    parser = argparse.ArgumentParser(description="Agent wrapper with chat auto-trigger")
    parser.add_argument("agent", choices=agent_names, help=f"Agent to wrap ({', '.join(agent_names)})")
    parser.add_argument("--no-restart", action="store_true", help="Do not restart on exit")
    parser.add_argument("--label", type=str, default=None, help="Custom display label")
    # Per-project isolation flags (must match the server's flags so wrappers
    # launched separately connect to the right instance). Values are consumed
    # by apply_cli_overrides() above; listing here so --help shows them.
    parser.add_argument("--data-dir",      default=None, help="Override server.data_dir (path)")
    parser.add_argument("--port",          default=None, help="Override server.port (int)")
    parser.add_argument("--mcp-http-port", default=None, help="Override mcp.http_port (int)")
    parser.add_argument("--mcp-sse-port",  default=None, help="Override mcp.sse_port (int)")
    parser.add_argument("--upload-dir",    default=None, help="Override images.upload_dir (path)")
    args, extra = parser.parse_known_args()

    agent = args.agent
    agent_cfg = config.get("agents", {}).get(agent, {})
    # scranton.sh passes the teammate's own git worktree here (see "worktree" in config.toml)
    cwd = os.environ.get("SCRANTON_CWD") or agent_cfg.get("cwd", ".")
    command = agent_cfg.get("command", agent)
    extra = [*extra, *_subagent_args(agent_cfg, command),
             *(_CODEX_ARGS if _provider_from_command(command) == "codex" else [])]
    data_dir = ROOT / config.get("server", {}).get("data_dir", "./data")
    _HANDOVER["command"] = command
    _HANDOVER["handoff_dir"] = data_dir / "handoffs"
    _HANDOVER["cwd"] = str((ROOT / cwd).expanduser().resolve()) if not str(cwd).startswith("~") else str(Path(cwd).expanduser().resolve())
    data_dir.mkdir(parents=True, exist_ok=True)
    server_port = config.get("server", {}).get("port", 8300)
    mcp_cfg = config.get("mcp", {})

    try:
        registration = _register_instance(server_port, agent, args.label)
    except Exception as exc:
        print(f"  Registration failed ({exc}).")
        print("  Wrapper cannot continue without a registered identity.")
        sys.exit(1)

    assigned_name = registration["name"]
    assigned_token = registration["token"]
    print(f"  Registered as: {assigned_name} (slot {registration.get('slot', '?')})")

    proxy = None
    proxy_url = None

    # Resolve MCP injection mode to determine if a proxy is needed.
    # Direct-connect modes (settings_file, env, flag) don't need a proxy.
    # proxy_flag mode needs a proxy. No mcp_inject = proxy fallback.
    inject_cfg = _resolve_mcp_inject(agent, agent_cfg)
    inject_mode = inject_cfg.get("mcp_inject", "")
    if inject_mode and inject_mode not in _VALID_INJECT_MODES:
        print(f"  Error: unknown mcp_inject mode '{inject_mode}' for agent '{agent}'.")
        print(f"  Valid modes: {', '.join(sorted(_VALID_INJECT_MODES))}")
        sys.exit(1)
    needs_proxy = inject_mode in ("proxy_flag", "") or not inject_mode

    if needs_proxy:
        from mcp_proxy import McpIdentityProxy

        transport = inject_cfg.get("mcp_transport", "http")
        if transport == "sse":
            upstream_base = f"http://127.0.0.1:{mcp_cfg.get('sse_port', 8201)}"
            proxy_path = "/sse"
        else:
            upstream_base = f"http://127.0.0.1:{mcp_cfg.get('http_port', 8200)}"
            proxy_path = "/mcp"

        proxy = McpIdentityProxy(
            upstream_base=upstream_base,
            upstream_path=proxy_path,
            agent_name=assigned_name,
            instance_token=assigned_token,
        )
        if proxy.start() is False:
            print("  Failed to start MCP proxy.")
            sys.exit(1)
        proxy_url = f"{proxy.url}{proxy_path}"

    _identity_lock = threading.Lock()
    _identity = {
        "name": assigned_name,
        "queue": data_dir / f"{assigned_name}_queue.jsonl",
        "token": assigned_token,
    }

    def get_identity():
        with _identity_lock:
            return _identity["name"], _identity["queue"]

    def get_token():
        with _identity_lock:
            return _identity["token"]

    # Rewrite MCP config when token/name changes (e.g. after 409 re-register).
    # Most CLIs won't re-read mid-session, but the file is correct for next restart.
    def _rewrite_mcp_config(instance_name: str, new_token: str):
        if not inject_mode or needs_proxy:
            return  # proxy-based agents don't have config files to rewrite
        try:
            _apply_mcp_inject(
                inject_cfg, instance_name, data_dir, proxy_url,
                token=new_token, mcp_cfg=mcp_cfg,
                project_dir=(ROOT / cwd).resolve(),
            )
        except Exception:
            pass

    def set_runtime_identity(new_name: str | None = None, new_token: str | None = None):
        with _identity_lock:
            old_name = _identity["name"]
            old_token = _identity["token"]
            changed = False
            if new_name and new_name != old_name:
                _identity["name"] = new_name
                _identity["queue"] = data_dir / f"{new_name}_queue.jsonl"
                changed = True
            if new_token and new_token != old_token:
                _identity["token"] = new_token
                changed = True
            current_name = _identity["name"]
            current_token = _identity["token"]

        if changed and proxy is not None:
            proxy.agent_name = current_name
            proxy.token = current_token
        if changed:
            if new_name and new_name != old_name:
                print(f"  Identity updated: {old_name} -> {new_name}")
            if new_token and new_token != old_token:
                print(f"  Session refreshed for @{current_name}")
            _rewrite_mcp_config(current_name, current_token)

        return changed

    # Scranton: keep work that arrived while this teammate was down (a crash, an update,
    # "Resume"), but only the last few items so a long outage doesn't replay a flood.
    queue_file = _identity["queue"]
    _taking = queue_file.with_name(queue_file.name + ".taking")
    if queue_file.exists() or _taking.exists():
        _dropped = _take_queue(queue_file, _taking, keep=5)
        if _dropped:
            print(f"  skipped {_dropped} older message(s) that arrived while I was stopped", flush=True)

    # Scranton: API keys are always stripped so the CLIs use your subscription,
    # even when the tmux server was started from a shell that has them set.
    from config_loader import PAID_API_ENV
    strip_vars = {"CLAUDECODE", *PAID_API_ENV} | set(agent_cfg.get("strip_env", []))
    env = {k: v for k, v in os.environ.items() if k not in strip_vars}

    resolved = shutil.which(command)
    if not resolved:
        print(f"  Error: '{command}' not found on PATH.")
        print("  Install it first, then try again.")
        sys.exit(1)
    command = resolved

    project_dir = (ROOT / cwd).resolve()

    # Gemini: ensure the project directory is trusted so MCPs are allowed.
    # Gemini blocks ALL MCPs for untrusted folders — even system-settings ones.
    if agent == "gemini" or inject_cfg.get("mcp_inject") == "env":
        _ensure_gemini_folder_trusted(project_dir)

    launch_args, env, inject_env, mcp_settings_path = _build_provider_launch(
        agent=agent,
        agent_cfg=agent_cfg,
        instance_name=assigned_name,
        data_dir=data_dir,
        proxy_url=proxy_url,
        extra_args=extra,
        env=env,
        token=assigned_token,
        mcp_cfg=mcp_cfg,
        project_dir=project_dir,
    )

    # Scranton: who commits. Every teammate commits with the bot account's email (so GitHub
    # shows the bot), under its own name (so you can see which teammate did it). Set through
    # GIT_CONFIG_* so `git config user.email` shows it too; nothing is written to any repo.
    git_email = str(config.get("team", {}).get("git_email", "")).strip()
    if git_email:
        git_name = f"{agent_cfg.get('label', agent)} (Scranton {agent})"
        inject_env = dict(inject_env or {})
        inject_env.update({
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": git_name,
            "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": git_email,
        })

    print(f"  === {assigned_name.capitalize()} Chat Wrapper ===")
    if not needs_proxy:
        print(f"  MCP: direct connect ({inject_mode}) with bearer auth")
        if mcp_settings_path:
            print(f"  Config: {mcp_settings_path}")
    elif proxy_url:
        print(f"  Local MCP proxy: {proxy_url}")
    print(f"  @{assigned_name} mentions auto-inject MCP reads")
    print(f"  Starting {command} in {cwd}...\n")

    def _heartbeat():
        while True:
            current_name, _ = get_identity()
            current_token = get_token()
            url = f"http://127.0.0.1:{server_port}/api/heartbeat/{current_name}"
            try:
                req = urllib.request.Request(
                    url,
                    method="POST",
                    data=b"",
                    headers=_auth_headers(current_token),
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp_data = json.loads(resp.read())
                server_name = resp_data.get("name", current_name)
                if server_name != current_name:
                    set_runtime_identity(server_name)
            except urllib.error.HTTPError as exc:
                if exc.code == 409:
                    try:
                        replacement = _register_instance(server_port, agent, args.label)
                        set_runtime_identity(replacement["name"], replacement["token"])
                        _notify_recovery(data_dir, replacement["name"])
                    except Exception:
                        pass
                time.sleep(5)
                continue
            except Exception:
                time.sleep(5)
                continue

            time.sleep(5)

    threading.Thread(target=_heartbeat, daemon=True).start()

    _watcher_inject_fn = None
    _watcher_thread = None
    _is_multi_instance = registration.get("slot", 1) > 1
    _trigger_flag = [False]  # shared: queue watcher sets True, activity checker reads
    _refresh_interval = 10  # default; overridden per-trigger by server settings
    # Scranton: role and team brief from config.toml
    _default_role = str(agent_cfg.get("role", "") or "").strip()
    # role_card: the agent's full rules (a file in this repo, e.g. roles/developer.md).
    # Only the path is sent; the agent reads the file itself.
    _card = str(agent_cfg.get("role_card", "") or "").strip()
    if _card:
        _card_path = (ROOT / _card).resolve()
        if _card_path.is_file():
            _default_role = (f"{_default_role} | " if _default_role else "") + \
                f"Full role card (the source of truth; read it before you start): {_card_path}"
        else:
            print(f"  Warning: role_card {_card} not found")
    _team_brief = str(config.get("team", {}).get("brief", "") or "").strip()
    _hc = str(config.get("team", {}).get("harness_core", "") or "").strip()
    _team_brief = _team_brief.replace("{harness_core}", os.path.expanduser(_hc) if _hc else "harness-core")
    _OWNER_DEFAULT[0] = str(config.get("team", {}).get("owner", "") or "the owner")

    def start_watcher(inject_fn):
        nonlocal _watcher_inject_fn, _watcher_thread
        _watcher_inject_fn = inject_fn
        _watcher_thread = threading.Thread(
            target=_queue_watcher,
            args=(get_identity, inject_fn),
            kwargs={"is_multi_instance": _is_multi_instance, "trigger_flag": _trigger_flag,
                    "server_port": server_port, "agent_name": assigned_name,
                    "get_token_fn": get_token, "refresh_interval": _refresh_interval,
                    "default_role": _default_role, "team_brief": _team_brief},
            daemon=True,
        )
        _watcher_thread.start()

    def _watcher_monitor():
        nonlocal _watcher_thread
        while True:
            time.sleep(5)
            if _watcher_thread and not _watcher_thread.is_alive() and _watcher_inject_fn:
                _watcher_thread = threading.Thread(
                    target=_queue_watcher,
                    args=(get_identity, _watcher_inject_fn),
                    kwargs={"is_multi_instance": _is_multi_instance, "trigger_flag": _trigger_flag,
                            "server_port": server_port, "agent_name": assigned_name,
                            "get_token_fn": get_token, "refresh_interval": _refresh_interval,
                    "default_role": _default_role, "team_brief": _team_brief},
                    daemon=True,
                )
                _watcher_thread.start()
                current_name, _ = get_identity()
                _notify_recovery(data_dir, current_name)

    threading.Thread(target=_watcher_monitor, daemon=True).start()
    # Scranton: pick up unfinished work after a restart, without a new @mention
    threading.Thread(target=_resume_unfinished, args=(queue_file, assigned_name, server_port, get_token),
                     daemon=True).start()

    _activity_checker = None

    def _set_activity_checker(checker):
        nonlocal _activity_checker
        _activity_checker = checker

    _describe = [None]       # set below on macOS/Linux: reads the agent's screen
    _exe = Path(str(command or "")).name.lower()   # "agent" is Cursor, "agy" is Antigravity ("my the app plan", 11-11)
    _app_name = {"claude": "Claude", "codex": "ChatGPT", "cursor": "Cursor", "agent": "Cursor", "cursor-agent": "Cursor",
                 "agy": "Antigravity"}.get(_exe, "the app")
    _reported = _PROBLEM_POSTED
    _seen = [None, 0.0]      # problem key on screen now, since when
    _idle_since = [None]     # went from working to idle at
    _checked_work = [None]   # the request we already checked for a missing reply
    _nudged = {}             # request time -> when we reminded the agent to reply

    _started_at = time.time()
    _frozen = {"sig": None, "since": 0.0, "told": False, "esc": False}   # stuck-command watch

    def _stuck_check(active: bool, now: float) -> str:
        """Lu, 11-12: motionintern showed "working" for an hour on a `cat << EOF` waiting for input.
        Working, yet the screen (digits ignored, so timers don't count as change) hasn't changed:
        at STUCK_TELL min say so in the channel; at STUCK_ESC min press Esc to stop the command.
        Returns the "doing" text to show while stuck ("" when not)."""
        if not active or not _HANDOVER.get("tmux"):
            _frozen.update(sig=None, since=0.0, told=False, esc=False)
            return ""
        try:
            from wrapper_unix import pane_text
            sig = _stuck_signature(pane_text(_HANDOVER["tmux"], 20))
        except Exception:
            return ""
        if sig != _frozen["sig"]:
            _frozen.update(sig=sig, since=now, told=False, esc=False)
            return ""
        mins = int((now - _frozen["since"]) // 60)
        if mins < STUCK_TELL:
            return ""
        last = next((l.strip() for l in reversed(pane_text(_HANDOVER["tmux"], 20).splitlines())
                     if l.strip() and not set(l.strip()) <= set("─━-│ ")), "")[:80]
        cur, _ = get_identity()
        if not _frozen["told"]:
            _frozen["told"] = True
            _post(server_port, cur, get_token(), _LAST_PLACE["channel"], _LAST_PLACE["thread"],
                  f"My screen hasn't changed for {mins} minutes while I'm \"working\": a command may be stuck "
                  f"(last line: {last}). I'll stop it myself at {STUCK_ESC} minutes; open my terminal to stop it sooner.")
        if mins >= STUCK_ESC and not _frozen["esc"]:
            _frozen["esc"] = True
            try:
                import subprocess
                subprocess.run(["tmux", "send-keys", "-t", _HANDOVER["tmux"], "Escape"], capture_output=True, timeout=5)
                _post(server_port, cur, get_token(), _LAST_PLACE["channel"], _LAST_PLACE["thread"],
                      f"Stopped a command that was stuck for {mins} minutes (pressed Esc). Picking up again.")
            except Exception:
                pass
        return f"Stuck? no change for {mins} min"

    def _work():
        try:
            return json.loads(_work_file(queue_file, assigned_name).read_text("utf-8")) or {}
        except (OSError, ValueError, NameError):
            return {}
    def _work_at():
        try:
            return float(_work().get("at") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _activity_monitor():
        last_active = None
        last_doing = None
        last_report_time = 0
        REPORT_INTERVAL = 3  # re-send state every 3s while active (keeps server lease fresh)
        while True:
            time.sleep(1)
            if not _activity_checker:
                continue
            try:
                active = _activity_checker()
                now = time.time()
                doing, problem = ("", None)
                if _describe[0]:
                    try:
                        doing, problem = _describe[0]()
                    except Exception:
                        doing, problem = ("", None)
                # Only when the same problem is still there a few seconds later and the
                # screen has stopped changing: one passing line isn't a stop.
                if problem != _seen[0]:
                    _seen[0], _seen[1] = problem, now
                if not problem and _seen[1] and now - _seen[1] > 60:
                    for k in ("limit", "model_limit", "api_credit"):
                        _reported.pop(k, None)   # gone from the screen: next time is a new one
                if problem and not active and now - _seen[1] >= 5 and now - _reported.get(problem, 0) > 1800:
                    # say it once where the agent was last asked; a limit is said once until it clears
                    _reported[problem] = now + (10 ** 9 if problem in ("limit", "model_limit", "api_credit") else 0)
                    from wrapper_unix import problem_text
                    cur, _ = get_identity()
                    if problem in ("limit", "model_limit", "api_credit"):
                        # Ask Scranton first: a warning isn't the end (keep going), a model that's out
                        # moves to one with room, then the backup API key; only then "I stopped".
                        verdict = _ask_limit_check(server_port, get_token(), _LAST_PLACE, problem)
                        if verdict == "ignore":
                            _reported[problem] = now - 1200   # look again in 10 minutes
                            continue
                        if verdict == "switched":
                            continue
                    if problem == "limit" and _LIMIT_API_OK[0] and _ask_api_fallback(server_port, get_token(), _LAST_PLACE):
                        continue
                    _post(server_port, cur, get_token(), _LAST_PLACE["channel"], _LAST_PLACE["thread"],
                          problem_text(problem, _app_name, _LIMIT_DETAIL[0]))
                # Worked on a request, went quiet for 90 s, never answered: say so once.
                if active:
                    _idle_since[0] = None
                elif last_active and _idle_since[0] is None:
                    _idle_since[0] = now
                if (_idle_since[0] and now - _idle_since[0] > 90 and not problem
                        and _checked_work[0] != _work_at()):
                    _checked_work[0] = _work_at()
                    w_at = _checked_work[0]
                    # Only work handed to THIS run: after a restart the request from before is gone
                    # from the CLI's memory, and the new run doesn't know its channel (11-09: everyone
                    # asked "what request?" in #general). Ask where the request came from, not #general.
                    w = _work()
                    w_ch, w_th = (w.get("channel") or _LAST_PLACE["channel"]), w.get("thread")
                    if w_at and w_at > _started_at and now - w_at < 6 * 3600:
                        cur, _ = get_identity()
                        try:
                            msgs = _read_channel(server_port, get_token(), w_ch)
                            if not _replied_since(msgs, cur, w_at):
                                if _nudged.get(w_at) is None and _watcher_inject_fn:
                                    # First ask the agent itself: often its reply just didn't reach
                                    # Scranton (e.g. Scranton was restarting). Only tell Lu if that fails.
                                    _nudged[w_at] = now
                                    _checked_work[0] = None   # check again after this nudge
                                    _watcher_inject_fn(_NUDGE.format(ch=w_ch))
                                else:
                                    _post(server_port, cur, get_token(), w_ch, w_th,
                                          "I stopped without replying, even after a reminder. Open my terminal to see where I am, or @ me again.")
                        except Exception:
                            pass   # Scranton unreachable: say nothing now, the next check will tell
                # Send on state change, periodically while active (refresh lease),
                # or periodically while idle (keep presence alive)
                IDLE_REPORT_INTERVAL = 8  # keep-alive while idle
                should_send = (
                    active != last_active
                    or (active and now - last_report_time >= REPORT_INTERVAL)
                    or (not active and now - last_report_time >= IDLE_REPORT_INTERVAL)
                    or (active and doing != last_doing)
                )
                stuck = _stuck_check(bool(active), now)
                if stuck:
                    doing = stuck
                    should_send = should_send or doing != last_doing
                if should_send:
                    current_name, _ = get_identity()
                    current_token = get_token()
                    url = f"http://127.0.0.1:{server_port}/api/heartbeat/{current_name}"
                    body = json.dumps({"active": active, "doing": doing if active else ""}).encode()
                    req = urllib.request.Request(
                        url,
                        method="POST",
                        data=body,
                        headers=_auth_headers(current_token, include_json=True),
                    )
                    resp = urllib.request.urlopen(req, timeout=5)
                    resp_code = resp.getcode()
                    last_active = active
                    last_doing = doing
                    last_report_time = now
            except Exception:
                pass

    threading.Thread(target=_activity_monitor, daemon=True).start()

    _agent_pid = [None]

    if sys.platform == "win32":
        from wrapper_windows import get_activity_checker, run_agent

        _set_activity_checker(get_activity_checker(_agent_pid, agent_name=assigned_name, trigger_flag=_trigger_flag))
    else:
        from wrapper_unix import get_activity_checker, run_agent

        unix_session_name = f"agentchattr-{assigned_name}"
        _HANDOVER["tmux"] = unix_session_name
        from wrapper_unix import describe_screen, is_working
        _describe[0] = lambda: describe_screen(unix_session_name)
        _HANDOVER["busy"] = lambda: is_working(unix_session_name)
        from wrapper_unix import question_text
        _ASKED[0] = lambda: question_text(unix_session_name)
        _set_activity_checker(get_activity_checker(
            unix_session_name, trigger_flag=_trigger_flag,
            provider=_provider_from_command(command),
        ))

    run_kwargs = dict(
        command=command,
        extra_args=launch_args,
        cwd=cwd,
        env=env,
        queue_file=queue_file,
        agent=agent,
        no_restart=args.no_restart,
        start_watcher=start_watcher,
        strip_env=list(strip_vars),
        pid_holder=_agent_pid,
        inject_env=inject_env,
        inject_delay=agent_cfg.get("inject_delay", 0.3),
    )
    # Windows-only injection tuning (no-op on other platforms).
    if sys.platform == "win32":
        run_kwargs["enter_backend"] = agent_cfg.get("enter_backend", "console_input")
    if sys.platform != "win32":
        run_kwargs["session_name"] = unix_session_name

    try:
        run_agent(**run_kwargs)
    finally:
        try:
            current_name, _ = get_identity()
            current_token = get_token()
            dereg_req = urllib.request.Request(
                f"http://127.0.0.1:{server_port}/api/deregister/{current_name}",
                method="POST",
                data=b"",
                headers=_auth_headers(current_token),
            )
            urllib.request.urlopen(dereg_req, timeout=5)
            print(f"  Deregistered {current_name}")
        except Exception:
            pass

        if proxy is not None:
            proxy.stop()

    print("  Wrapper stopped.")


if __name__ == "__main__":
    main()
