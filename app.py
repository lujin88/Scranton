"""agentchattr — FastAPI web UI + agent auto-trigger."""

from safe_io import atomic_write, quarantine
import os
import asyncio
import json
import re as _re
import time as _time_feed
_VIA_RE = _re.compile(r"[a-z][a-z0-9 -]{0,19}")   # "via Claude": who sent a message on your behalf
import sys
import threading
import uuid
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from store import MessageStore
from rules import RuleStore
from summaries import SummaryStore
from jobs import JobStore
from schedules import ScheduleStore, parse_schedule_spec
import scranton_quota as _sc_quota
import scranton_due as _sc_due_mod
import scranton_quota_ask as _sc_qask
import scranton_apikeys as _sc_keys
from router import Router
from agents import AgentTrigger
from registry import RuntimeRegistry
from session_store import SessionStore, validate_session_template
from session_engine import SessionEngine

log = logging.getLogger(__name__)

app = FastAPI(title="Scranton")

# --- globals (set by configure()) ---
store: MessageStore | None = None
rules: RuleStore | None = None
summaries: SummaryStore | None = None
jobs: JobStore | None = None
schedules: ScheduleStore | None = None
router: Router | None = None
agents: AgentTrigger | None = None
registry: RuntimeRegistry | None = None
session_store: SessionStore | None = None
session_engine: SessionEngine | None = None
config: dict = {}
ws_clients: set[WebSocket] = set()

# --- Security: session token (set by configure()) ---
session_token: str = ""

# Room settings (persisted to data/settings.json)
room_settings: dict = {
    "title": "Scranton",
    # Shown beside the title, so several servers can be told apart without
    # renaming the product itself. "" hides it.
    "subtitle": "",
    "username": "user",
    "font": "sans",
    "channels": ["general"],
    "history_limit": "all",
    "contrast": "normal",
    "custom_roles": [],
}

HISTORY_CAP = 1000  # messages per channel sent when a page opens
INITIAL_HISTORY = 150   # ...of which the page gets this many now; older ones load on scroll-up

# Channel validation
_CHANNEL_NAME_RE = _re.compile(r'^[a-z0-9][a-z0-9\-]{0,19}$')

# Agent hats (persisted to data/hats.json)
agent_hats: dict[str, str] = {}  # { agent_name: svg_string }


def _hats_path() -> Path:
    data_dir = config.get("server", {}).get("data_dir", "./data")
    return Path(data_dir) / "hats.json"


def _load_hats():
    # Scranton: hats are off. They were inline SVG from agents, which can carry script.
    global agent_hats
    agent_hats = {}


def _save_hats():
    p = _hats_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(agent_hats), "utf-8")


def _sanitize_svg(svg: str) -> str:
    """Strip dangerous content from SVG string."""
    svg = _re.sub(r'<script[^>]*>.*?</script>', '', svg, flags=_re.DOTALL | _re.IGNORECASE)
    svg = _re.sub(r'\bon\w+\s*=', '', svg, flags=_re.IGNORECASE)
    svg = _re.sub(r'javascript\s*:', '', svg, flags=_re.IGNORECASE)
    return svg


def set_agent_hat(agent: str, svg: str) -> str | None:
    """Validate, sanitize, and store a hat SVG. Returns error string or None."""
    return "Hats are turned off in Scranton."
    svg = svg.strip()
    if not svg.lower().startswith("<svg"):
        return "Hat must be an SVG element (starts with <svg)."
    if len(svg) > 5120:
        return "Hat SVG too large (max 5KB)."
    svg = _sanitize_svg(svg)
    agent_hats[agent.lower()] = svg
    _save_hats()
    if _event_loop:
        asyncio.run_coroutine_threadsafe(broadcast_hats(), _event_loop)
    return None


def clear_agent_hat(agent: str):
    """Remove an agent's hat."""
    key = agent.lower()
    if key in agent_hats:
        del agent_hats[key]
        _save_hats()
        if _event_loop:
            asyncio.run_coroutine_threadsafe(broadcast_hats(), _event_loop)


def _settings_path() -> Path:
    data_dir = config.get("server", {}).get("data_dir", "./data")
    return Path(data_dir) / "settings.json"


ROOM_SUBTITLE_MAX = 40


def normalize_room_subtitle(value):
    """Clean a room subtitle, or return None if it is not usable.

    Collapses any internal whitespace so a pasted newline cannot break the
    header across two lines, and caps the length so a long name cannot crowd
    out the rest of the header.
    """
    if not isinstance(value, str):
        return None
    return " ".join(value.split())[:ROOM_SUBTITLE_MAX]


def apply_room_subtitle(new: dict):
    """Apply a subtitle from a settings payload, if present and usable."""
    if "subtitle" not in new:
        return
    cleaned = normalize_room_subtitle(new["subtitle"])
    if cleaned is not None:
        room_settings["subtitle"] = cleaned


def _load_settings():
    global room_settings
    p = _settings_path()
    if p.exists():
        try:
            saved = json.loads(p.read_text("utf-8"))
            room_settings.update(saved)
        except Exception:
            moved = quarantine(p)   # keep the broken file instead of overwriting it
            print(f"  settings.json couldn't be read; kept a copy at {moved}")
    # settings.json is hand-editable, so the file bypasses every check the
    # live update path applies. Re-normalise on load rather than trust it.
    room_settings["subtitle"] = normalize_room_subtitle(room_settings.get("subtitle")) or ""
    # Ensure "general" always exists and is first
    if "channels" not in room_settings or not room_settings["channels"]:
        room_settings["channels"] = ["general"]
    elif "general" not in room_settings["channels"]:
        room_settings["channels"].insert(0, "general")
    # Scranton: your display name defaults to [team].owner until you change it.
    _owner = str((config or {}).get("team", {}).get("owner", "") or "").strip()
    if _owner and room_settings.get("username", "user") == "user":
        room_settings["username"] = _owner[:20]
    # Scranton: channels listed under [team].channels in config.toml always
    # exist. Channels you add in the UI are kept too; nothing is removed.
    # Each one is added once; if you later delete or rename it, it stays gone.
    seeded = set(room_settings.get("seeded_channels", []) or [])
    for ch in (config or {}).get("team", {}).get("channels", []) or []:
        ch = str(ch).strip().lower()
        if not _CHANNEL_NAME_RE.match(ch) or ch in seeded:
            continue
        if ch not in room_settings["channels"]:
            room_settings["channels"].append(ch)
        seeded.add(ch)
    room_settings["seeded_channels"] = sorted(seeded)

    # Scranton: who is in each channel. [team.members] in config.toml fills a channel the
    # first time; after that Lu's adds and removes in the UI are kept.
    members = room_settings.get("channel_members")
    if not isinstance(members, dict):
        members = {}
    known = set((config or {}).get("agents", {}))
    seeded_m = set(room_settings.get("seeded_members", []) or [])
    for ch, names in ((config or {}).get("team", {}).get("members", {}) or {}).items():
        ch = str(ch).strip().lower()
        if ch in seeded_m or not isinstance(names, list):
            continue
        cur = [n for n in members.get(ch, []) if n in known]
        for n in names:
            n = str(n).strip().lower()
            if n in known and n not in cur:
                cur.append(n)
        members[ch] = cur
        seeded_m.add(ch)
    room_settings["channel_members"] = {ch: [n for n in ns if n in known] for ch, ns in members.items()
                                        if isinstance(ns, list)}
    room_settings["seeded_members"] = sorted(seeded_m)


_last_logged: dict = {}


def _log_rate_limited(what: str, every: float = 300):
    """log.exception at most once per `every` seconds per kind: loud enough to find, not a flood."""
    import time as _t
    now = _t.time()
    if now - _last_logged.get(what, 0) >= every:
        _last_logged[what] = now
        log.exception(what)


def _label_of(name: str) -> str:
    """The name Lu sees for a teammate (its label), not the handle."""
    base = str(name).split("-")[0]
    agents_cfg = (config or {}).get("agents", {}) or {}
    return str((agents_cfg.get(name) or agents_cfg.get(base) or {}).get("label") or name)


def _report_start(res: dict, channel: str, why: str):
    """Tell the channel which teammates are starting and which can't."""
    team = (config or {}).get("agents", {})
    label = lambda n: str(team.get(n, {}).get("label", n))
    if res.get("started"):
        names = "、".join(label(n) for n in res["started"])
        store.add("system", f"Starting {names}. They'll reply in a few seconds.",
                  msg_type="system", channel=channel)
    for n, reason in (res.get("failed") or {}).items():
        store.add("system", f"{label(n)} can't start: {reason}.", msg_type="system", channel=channel)


def _channel_members(ch: str) -> list[str]:
    return list((room_settings.get("channel_members") or {}).get(ch, []))


def _add_members(ch: str, names: list[str]) -> list[str]:
    """Add configured teammates to a channel. Returns the ones that were new."""
    if ch.startswith("dm-") or ch not in room_settings.get("channels", []):
        return []
    known = (config or {}).get("agents", {})
    cur = _channel_members(ch)
    added = [n for n in dict.fromkeys(names) if n in known and n not in cur]
    if added:
        room_settings.setdefault("channel_members", {})[ch] = cur + added
    return added


# Texts that shipped before Scranton remembered what it seeded, so old installs still update.
_OLD_SCHEDULE_TEXTS = {
    "daily-plan": "今日计划：按 handoff.md「下一步」和各人手上的活，列出今天每个人做什么（谁｜做什么｜要不要等 Lu），最后一行写今天需要 @Lu 决定的事（没有就写没有）。不超过 10 行。",
    "daily-summary": "每日总结：今天做完了什么（附 PR 链接）｜卡在哪、谁卡住了｜等 Lu 决定的事｜明天先做什么。只写真实发生的，不超过 10 行，最后 @Lu。",
}


def _seed_team_schedules(cfg: dict):
    """Scranton: [[team.schedules]] in config.toml become recurring posts, e.g. the 21:00
    "@pm daily backup" that harness-core asks for. Each one is created once (keyed by its
    'id'); deleting it in the UI keeps it deleted. Posted by "Scranton", so no teammate
    has to stay awake for it."""
    if not schedules:
        return
    seeded = set(room_settings.get("seeded_schedules", []) or [])
    if getattr(schedules, "lost", False):
        seeded = set()   # schedules.json was unreadable: bring the built-in ones back
    changed = False
    for item in (cfg or {}).get("team", {}).get("schedules", []) or []:
        sid = str(item.get("id", "")).strip()
        at = str(item.get("daily_at", "")).strip()
        to = [str(t).strip().lower() for t in (item.get("to") or []) if str(t).strip()]
        text = str(item.get("text", "")).strip()
        if not sid or sid in seeded or not _re.fullmatch(r"\d{1,2}:\d{2}", at) or not to or not text:
            continue
        try:
            created = schedules.create(prompt=text, targets=to, channel=str(item.get("channel", "general")),
                                       interval_seconds=86400, daily_at=at, created_by="Scranton")
        except ValueError:
            continue
        room_settings.setdefault("seeded_schedule_ids", {})[sid] = created.get("id")
        seeded.add(sid)
        changed = True
    # The 21:00 backup used to carry the summary too; the summary is its own post now.
    for s in schedules.list_all():
        if s.get("created_by") == "Scranton" and str(s.get("prompt", "")).startswith("每日备份和每日总结"):
            new = next((str(i.get("text", "")) for i in (cfg or {}).get("team", {}).get("schedules", []) or [] if i.get("id") == "daily-backup"), "")
            if new:
                schedules.set_fields(s["id"], prompt=new)
                room_settings.setdefault("seeded_schedule_ids", {})["daily-backup"] = s["id"]
                changed = True
    # Config text changed since it was seeded: update the post, unless Lu edited it in the UI.
    texts = room_settings.setdefault("seeded_schedule_texts", {})
    live = {s.get("id"): s for s in schedules.list_all()}
    for item in (cfg or {}).get("team", {}).get("schedules", []) or []:
        sid = str(item.get("id", "")).strip()
        text = str(item.get("text", "")).strip()
        sched = live.get((room_settings.get("seeded_schedule_ids", {}) or {}).get(sid))
        if not sid or not text or not sched:
            continue
        base = texts.get(sid) or _OLD_SCHEDULE_TEXTS.get(sid, text)
        if sched.get("prompt") == base and base != text:
            schedules.set_fields(sched["id"], prompt=text)
            changed = True
        if texts.get(sid) != text and sched.get("prompt") in (base, text):
            texts[sid] = text
            changed = True
    if changed:
        room_settings["seeded_schedules"] = sorted(seeded)
        _save_settings()


def _daily_ids(cfg: dict) -> list[str]:
    ids = room_settings.get("seeded_schedule_ids", {}) or {}
    daily = [str(i.get("id")) for i in (cfg or {}).get("team", {}).get("schedules", []) or [] if i.get("daily")]
    return [ids[d] for d in daily if d in ids]


def _save_settings():
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(room_settings, indent=2), "utf-8")


def _extract_agent_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-agent-token", "").strip()


def _resolve_authenticated_agent(request: Request) -> dict | None:
    if not registry:
        return None
    token = _extract_agent_token(request)
    if not token:
        return None
    return registry.resolve_token(token)


# --- Security middleware ---
# Paths that don't require the session token (public assets).
_PUBLIC_PREFIXES = ("/", "/static/")


def _install_security_middleware(token: str, cfg: dict):
    """Add token validation and origin checking middleware to the app."""
    import app as _self
    _self.session_token = token
    port = cfg.get("server", {}).get("port", 8300)
    allowed_origins = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    }
    # Scranton: extra origins for phone access through Tailscale Serve,
    # e.g. "https://mac-mini.tail1234.ts.net". Exact match only, no wildcards.
    for extra in cfg.get("server", {}).get("allowed_origins", []) or []:
        extra = str(extra).strip().rstrip("/")
        if extra:
            allowed_origins.add(extra)

    # Scranton: Host header allow-list for the pages that hand out or use the
    # session token (DNS-rebinding guard). Built from the same origins.
    from urllib.parse import urlsplit
    allowed_hosts = set()
    for o in allowed_origins:
        parts = urlsplit(o)
        if parts.netloc:
            allowed_hosts.add(parts.netloc.lower())
            allowed_hosts.add(parts.hostname.lower())
    _self.allowed_hosts = allowed_hosts
    _self.allowed_ws_origins = set(allowed_origins)

    class SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            # Scranton: every path, not only "/", must come to a known host (DNS rebinding),
            # and a browser request from another site is refused before anything else,
            # including the loopback-only agent routes (a web page can't register agents).
            host = request.headers.get("host", "").lower()
            if host not in allowed_hosts:
                return JSONResponse({"error": f"forbidden: unknown host {host!r}. To open Scranton from this address, add https://{host} to [server] allowed_origins in config.local.toml and restart."}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin not in allowed_origins:
                return JSONResponse({"error": "forbidden: origin not allowed"}, status_code=403)
            # Only Lu's own Tailscale login may come in through Tailscale Serve, when set.
            owner_login = str(cfg.get("server", {}).get("owner_login", "") or "").strip().lower()
            if owner_login:
                proxied = any(h in request.headers for h in ("x-forwarded-for", "forwarded", "x-real-ip", "tailscale-user-login"))
                if proxied and request.headers.get("tailscale-user-login", "").strip().lower() != owner_login:
                    return JSONResponse({"error": "forbidden: this Scranton belongs to someone else on the tailnet"}, status_code=403)

            # Static assets, index page, and uploaded images are public.
            # The index page injects the token client-side via same-origin script.
            # Images keep their public preview URLs. Other attachments require
            # the browser session token, like the rest of the API.
            public_image = path.startswith("/uploads/") and Path(path).suffix.lower() in IMAGE_UPLOAD_EXTS
            if path == "/" or path.startswith("/static/") or public_image:
                return await call_next(request)
            # Scranton: only *reading* roles is public (the wrapper reads them without a token).
            # Writing a role changes what full-permission agents are told, so POST goes through
            # the origin + session-token checks below like every other write.
            if path == "/api/roles" and request.method == "GET":
                return await call_next(request)

            # Agent registration/heartbeat: loopback only (no remote agent minting).
            if path.startswith(("/api/register", "/api/deregister/", "/api/heartbeat/")):
                client_ip = request.client.host if request.client else ""
                # Scranton: Tailscale Serve proxies phone traffic from 127.0.0.1,
                # so a proxied request must not count as local.
                proxied = any(h in request.headers for h in
                              ("x-forwarded-for", "forwarded", "x-real-ip", "tailscale-user-login"))
                if client_ip not in ("127.0.0.1", "::1", "localhost") or proxied:
                    return JSONResponse(
                        {"error": f"forbidden: agent registration is restricted to local loopback. Source {client_ip} is not allowed."},
                        status_code=403,
                    )
                return await call_next(request)

            # --- Origin check (blocks cross-origin / DNS-rebinding attacks) ---
            origin = request.headers.get("origin")
            if origin and origin not in allowed_origins:
                return JSONResponse(
                    {"error": "forbidden: origin not allowed"},
                    status_code=403,
                )

            # --- Token check ---
            # Allow registered agents to authenticate via Bearer token
            # for /api/messages and /api/send (no browser session needed).
            auth_header = request.headers.get("authorization", "")
            agent_ok = (path in AGENT_BEARER_PATHS or path.startswith("/api/rules/")
                        or (path == "/api/scranton/handover" and request.method == "GET"))   # wrappers read when to hand over
            if auth_header.lower().startswith("bearer ") and agent_ok:
                bearer = auth_header[7:].strip()
                if _self.registry and _self.registry.resolve_token(bearer):
                    return await call_next(request)

            # Scranton: Grok Bot's command (scranton.sh grok) has its own token, for its own routes only.
            if path.startswith("/api/scranton/grok/") and _sc_grok.check(request.headers.get("x-grok-token", "")):
                return await call_next(request)

            req_token = (
                request.headers.get("x-session-token")
                or request.query_params.get("token")
            )
            if req_token != _self.session_token:
                return JSONResponse(
                    {"error": "forbidden: invalid or missing session token"},
                    status_code=403,
                )

            return await call_next(request)

    app.add_middleware(SecurityMiddleware)


# Routes a wrapper may call with its agent token instead of the browser session token. Every
# route a wrapper calls with "Authorization: Bearer" must be here (tests/test_agent_routes.py checks).
# 11-11: limit-check was missing, so every check came back 403; the wrapper read that as "the plan
# is used up" and posted "I stopped" at 79 % of the week.
AGENT_BEARER_PATHS = ("/api/messages", "/api/send", "/api/scranton/api-fallback", "/api/scranton/limit-check")


def configure(cfg: dict, session_token: str = ""):
    global store, rules, summaries, jobs, schedules, router, agents, registry, session_store, session_engine, config
    config = cfg
    # --- Security: store the session token and install middleware ---
    _install_security_middleware(session_token, cfg)

    data_dir = cfg.get("server", {}).get("data_dir", "./data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    log_path = Path(data_dir) / "agentchattr_log.jsonl"
    legacy_log_path = Path(data_dir) / "room_log.jsonl"
    if not log_path.exists() and legacy_log_path.exists():
        # Backward compatibility for existing installs.
        log_path = legacy_log_path

    # Scranton: an imported chat history is put in place before it's loaded.
    raw_upload_dir = cfg.get("images", {}).get("upload_dir", "./uploads")
    try:
        _sc_backup.apply_pending(data_dir, raw_upload_dir)
    except Exception as e:
        print(f"  Import of chat history didn't finish: {e}")
    _sc_backup.setup(data_dir, raw_upload_dir)
    _sc_presence.setup(data_dir)
    _sc_shortcuts.setup(data_dir)
    _sc_grok.setup(data_dir)
    _sc_grok.token()   # so `scranton.sh grok` finds it
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        _sc_backup.start_daily()

    store = MessageStore(str(log_path))
    # Initialize store upload dir from config
    store.upload_dir = Path(raw_upload_dir)
    
    # Rules store — migrates from legacy decisions.json automatically
    rules_path = Path(data_dir) / "rules.json"
    legacy_decisions = Path(data_dir) / "decisions.json"
    if not rules_path.exists() and legacy_decisions.exists():
        legacy_decisions.rename(rules_path)
    rules = RuleStore(str(rules_path))
    rules.on_change(_on_rule_change)

    summaries = SummaryStore(str(Path(data_dir) / "summaries.json"))

    # Migrate legacy activities.json → jobs.json
    jobs_path = Path(data_dir) / "jobs.json"
    legacy_activities = Path(data_dir) / "activities.json"
    if not jobs_path.exists() and legacy_activities.exists():
        legacy_activities.rename(jobs_path)

    jobs = JobStore(str(jobs_path))
    jobs.on_change(_on_job_change)

    schedules = ScheduleStore(str(Path(data_dir) / "schedules.json"))
    schedules.on_change(_on_schedule_change)

    max_hops = cfg.get("routing", {}).get("max_agent_hops", 4)

    # Registry: single source of truth for all live agent state
    registry = RuntimeRegistry(data_dir=data_dir)
    registry.seed(cfg.get("agents", {}))
    registry.on_change(_on_registry_change)

    # Router starts with base agent names (backward compat for direct MCP users),
    # registry.on_change updates it dynamically when instances register/deregister
    agent_names = list(cfg.get("agents", {}).keys())
    router = Router(
        agent_names=agent_names,
        default_mention=cfg.get("routing", {}).get("default", "none"),
        max_hops=max_hops,
        online_checker=lambda: set(registry.get_active_names()) if registry else set(),
    )
    agents = AgentTrigger(registry, data_dir=data_dir)

    # Sessions
    ROOT = Path(__file__).parent
    session_store = SessionStore(
        str(Path(data_dir) / "session_runs.json"),
        templates_dir=str(ROOT / "session_templates"),
    )
    session_engine = SessionEngine(session_store, store, agents, registry)
    session_store.on_change(_on_session_change)

    # Bridge: when ANY message is added to store (including via MCP),
    # broadcast to all WebSocket clients
    store.on_message(_on_store_message)

    _load_settings()
    _seed_team_schedules(cfg)  # after settings load, so "already seeded" is remembered
    # The rollback point (data/run/prev_head) is dropped by scranton.sh only once the new
    # server has answered twice; see restart-server.
    _load_hats()

    # Apply saved loop guard setting
    if "max_agent_hops" in room_settings:
        router.max_hops = room_settings["max_agent_hops"]

    # Background thread: check for wrapper recovery flag files
    _data_dir = Path(data_dir)

    _known_online: set[str] = set()  # agents we've seen join — track for leave messages
    _posted_leave: set[str] = set()  # agents we've already posted a leave for — debounce

    _known_active = set()

    def _background_checks():
        import time as _time
        import mcp_bridge

        while True:
            _time.sleep(3)
            # Recovery flags
            try:
                for flag in _data_dir.glob("*_recovered"):
                    agent_name = flag.read_text("utf-8").strip()
                    flag.unlink()
                    store.add(
                        "system",
                        f"{_label_of(agent_name)} restarted after a problem. "
                        "If they don't reply, send your message again."
                    )
            except Exception:
                pass

            # Pending instances (slot 2+) wait for human naming or agent claim.
            # No auto-confirm — identity must be explicitly resolved.

            # Presence expiry — post leave messages (but do NOT deregister).
            # Deregistration only happens via /api/deregister (wrapper shutdown)
            # OR the 60s crash timeout below.
            # Short timeout (10s) prevents slot theft when MCP tool calls are intermittent.
            try:
                now = _time.time()
                with mcp_bridge._presence_lock:
                    currently_online = {
                        name for name, ts in mcp_bridge._presence.items()
                        if now - ts < mcp_bridge.PRESENCE_TIMEOUT
                    }
                    currently_active = set()
                    for name, active in mcp_bridge._activity.items():
                        if active:
                            if now - mcp_bridge._activity_ts.get(name, 0) < mcp_bridge.ACTIVITY_TIMEOUT:
                                currently_active.add(name)
                            else:
                                mcp_bridge._activity[name] = False  # auto-expire

                # Crash timeout: if a wrapper hasn't heartbeated for 60s,
                # it's dead — deregister it to free the slot.
                _CRASH_TIMEOUT = 15
                registered = set(registry.get_all_names())
                for name in registered:
                    with mcp_bridge._presence_lock:
                        last_seen = mcp_bridge._presence.get(name, 0)
                    if last_seen > 0 and now - last_seen > _CRASH_TIMEOUT:
                        log.info(f"Crash timeout: deregistering {name} (no heartbeat for {_CRASH_TIMEOUT}s)")
                        # Sleep / crash path: keep the token reclaimable so the
                        # wrapper transparently recovers its identity on wake.
                        # (A deliberate /api/deregister below stays non-reclaimable.)
                        result = registry.deregister(name, reclaimable=True)
                        if result:
                            mcp_bridge.purge_identity(name)
                            registry.clean_renames_for(name)
                            renamed = result.get("_renamed_back")
                            if renamed:
                                mcp_bridge.migrate_identity(renamed["old"], renamed["new"])
                                store.rename_sender(renamed["old"], renamed["new"])
                                _migrate_agent_last_channel(renamed["old"], renamed["new"])
                                if _event_loop:
                                    rename_event = json.dumps({
                                        "type": "agent_renamed",
                                        "old_name": renamed["old"],
                                        "new_name": renamed["new"],
                                    })
                                    asyncio.run_coroutine_threadsafe(_broadcast(rename_event), _event_loop)
                            store.add(name, f"{name} disconnected (timeout)", msg_type="leave", channel=_agent_last_channel.get(name, _last_active_channel))
                            _posted_leave.add(name)

                # Re-fetch registered names (may have changed from crash timeout above)
                registered = set(registry.get_all_names())

                # Detect registered instances going offline (leave message only)
                timed_out = registered - currently_online
                for name in timed_out:
                    inst = registry.get_instance(name)
                    if not inst:
                        continue
                    # Skip names that were just renamed (not actually offline)
                    with mcp_bridge._presence_lock:
                        was_renamed = name in mcp_bridge._renamed_from
                        if was_renamed:
                            mcp_bridge._renamed_from.discard(name)
                    if was_renamed:
                        continue
                    # Post leave message ONCE per offline transition (debounced)
                    if name not in _posted_leave:
                        _posted_leave.add(name)
                        store.add(name, f"{name} disconnected", msg_type="leave", channel=_agent_last_channel.get(name, _last_active_channel))

                # Clear leave debounce for agents that came back online
                _posted_leave.difference_update(currently_online)

                # Detect other agents (non-registered) going offline
                went_offline = (_known_online - currently_online) - timed_out
                for name in went_offline:
                    # Skip leave messages for names that were just renamed
                    with mcp_bridge._presence_lock:
                        was_renamed = name in mcp_bridge._renamed_from
                        if was_renamed:
                            mcp_bridge._renamed_from.discard(name)
                    if was_renamed:
                        continue
                    if not registry.is_registered(name) and name not in _posted_leave:
                        _posted_leave.add(name)
                        store.add(name, f"{name} disconnected", msg_type="leave", channel=_agent_last_channel.get(name, _last_active_channel))

                if _known_online != currently_online and _event_loop:
                    asyncio.run_coroutine_threadsafe(broadcast_status(), _event_loop)

                # Clear stale activity for agents that went offline
                with mcp_bridge._presence_lock:
                    stale_active = [n for n in mcp_bridge._activity
                                    if mcp_bridge._activity.get(n) and n not in currently_online]
                    for n in stale_active:
                        mcp_bridge._activity[n] = False
                    if stale_active:
                        currently_active -= set(stale_active)

                # Broadcast status on any change (online set or activity set)
                if currently_active != _known_active or _known_online != currently_online:
                    _known_active.clear()
                    _known_active.update(currently_active)
                    if _event_loop:
                        asyncio.run_coroutine_threadsafe(broadcast_status(), _event_loop)
                _known_online.clear()
                _known_online.update(currently_online)
            except Exception:
                _log_rate_limited("presence check failed")

    threading.Thread(target=_background_checks, daemon=True).start()

    # Report → Tokens: read the Claude Code / Codex logs once in the background after a start, so
    # the Report doesn't wait ~30 s the first time (every update restarts the server).
    def _warm_tokens():
        import time as _tw
        _tw.sleep(20)
        try:
            owner = str(room_settings.get("username") or config.get("team", {}).get("owner", "Lu"))
            _sc_tokens.build(store.get_since(-1), dict(config.get("agents", {})), owner, 7)
        except Exception:
            _log_rate_limited("token warm-up failed")
    threading.Thread(target=_warm_tokens, daemon=True).start()

    # --- Schedule runner: fires due scheduled prompts every 30s ---
    def _schedule_runner():
        import time as _time
        while True:
            _time.sleep(30)
            try:
                if not schedules:
                    continue
                due = schedules.run_due()
                for s in due:
                    prompt = s.get("prompt", "")
                    targets = s.get("targets", [])
                    channel = s.get("channel", "general")
                    if not prompt or not targets:
                        schedules.mark_run(s["id"])
                        continue
                    sender = s.get("created_by", "user")
                    mention_str = " ".join(f"@{t}" for t in targets)
                    full_text = f"{mention_str} {prompt}" if mention_str else prompt
                    # Scranton: missed while the Mac slept → say it's late, not pretend.
                    late = _time.time() - float(s.get("next_run", 0) or 0)
                    if s.get("daily_at") and late > 3 * 3600:
                        # Hours late (the Mac slept through it): an evening summary showing up
                        # next morning is noise. Skip it; it runs again at its next time.
                        schedules.mark_run(s["id"])
                        continue
                    if s.get("daily_at") and late > 600:
                        full_text += f" (missed {s.get('daily_at')}, running now)"
                    # Mark it run first: a crash right after posting must not post it twice.
                    if s.get("one_shot"):
                        schedules.delete(s["id"])
                    else:
                        schedules.mark_run(s["id"])
                    # store.add triggers _handle_new_message via callback,
                    # which routes @mentions to agents — no manual trigger needed.
                    store.add(
                        sender,
                        full_text,
                        channel=channel,
                    )
            except Exception:
                log.exception("schedule runner error")

    threading.Thread(target=_schedule_runner, daemon=True).start()

    # ChatGPT plan watch: once a minute, read Agent Monitor's usage file; when it crosses
    # the threshold either way, tell the project manager once.
    def _quota_watch():
        import time as _tq
        while True:
            try:
                low, changed = _sc_quota.check(config)
                if changed:
                    store.add("scranton", _sc_quota.notice(config, low), channel="general")
            except Exception:
                _log_rate_limited("quota watch failed")
            _tq.sleep(60)
    threading.Thread(target=_quota_watch, daemon=True).start()


# --- Store → WebSocket bridge ---

_event_loop = None  # set by run.py after starting the event loop
_last_active_channel: str = "general"  # last channel any message was sent in
# Per-agent last channel: where each sender was most recently active. Used to
# route leave/disconnect messages to the channel that agent was talking in,
# instead of the global last-active channel (which is usually #general and made
# leave spam land in the wrong place).
_agent_last_channel: dict[str, str] = {}


def _migrate_agent_last_channel(old_name: str, new_name: str):
    """Re-key _agent_last_channel across an agent rename.

    Without this, a disconnect for the post-rename name misses the map and
    falls back to the global last-active channel — putting the leave message
    back in the wrong channel. Call this beside every migrate_identity /
    rename_sender path (slot-1 rename, renamed-back, websocket rename_agent,
    /api/label)."""
    if old_name == new_name:
        return
    ch = _agent_last_channel.pop(old_name, None)
    if ch is not None:
        _agent_last_channel[new_name] = ch


def set_event_loop(loop):
    global _event_loop
    _event_loop = loop


def _on_store_message(msg: dict):
    """Called from any thread when a message is added to the store."""
    if _event_loop is None:
        return
    try:
        # If called from the event loop thread (e.g. WebSocket handler),
        # schedule directly as a task
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(_handle_new_message(msg))
            return
    except RuntimeError:
        pass  # No running loop — we're in a different thread (MCP)
    asyncio.run_coroutine_threadsafe(_handle_new_message(msg), _event_loop)


def _on_rule_change(action: str, rule: dict):
    """Called from any thread when a rule changes."""
    if _event_loop is None:
        return
    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_rule(action, rule))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_rule(action, rule), _event_loop)


def _on_job_change(action: str, data: dict):
    """Called from any thread when a job changes."""
    if _event_loop is None:
        return
    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_job(action, data))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_job(action, data), _event_loop)


def _on_schedule_change(action: str, schedule: dict):
    """Called from any thread when a schedule changes."""
    if _event_loop is None:
        return
    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_schedule(action, schedule))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_schedule(action, schedule), _event_loop)


def _on_session_change(action: str, session: dict):
    """Called from any thread when a session changes."""
    if _event_loop is None:
        return
    # Enrich with computed fields so the frontend gets phase_name, current_agent, etc.
    if session_engine:
        session = session_engine._enrich(dict(session))

    # Add completion/interruption banners to chat timeline
    if action == "complete" and store:
        output_id = session.get("output_message_id")
        # Tag the output message so it renders highlighted on reload
        if output_id:
            msg = store.get_by_id(output_id)
            if msg:
                meta = msg.get("metadata") or {}
                meta["session_output"] = True
                store.update_message(output_id, {"metadata": meta})
        store.add(
            sender="system",
            text=f"Session complete: {session.get('template_name', '?')}",
            msg_type="session_end",
            channel=session.get("channel", "general"),
            metadata={"session_id": session.get("id"), "output_message_id": output_id},
        )
    elif action == "interrupt" and store:
        reason = session.get("interrupt_reason", "interrupted")
        store.add(
            sender="system",
            text=f"Session ended: {session.get('template_name', '?')} ({reason})",
            msg_type="session_end",
            channel=session.get("channel", "general"),
            metadata={"session_id": session.get("id"), "reason": reason},
        )

    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_session(action, session))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_session(action, session), _event_loop)


_draft_ref_re = _re.compile(r'\[([a-f0-9]{8})\]')

def _resolve_draft_lineage(text: str, channel: str) -> tuple[str, int]:
    """Check if a session draft block is a revision of an existing draft.

    Looks at the agent's own message text for a [draft_id] reference, and also
    scans recent channel messages for "revise session draft [XXXX]" requests.
    Returns (draft_id, revision). New drafts get a fresh id and revision=1.
    """
    # Check the message text itself for a draft_id reference
    ref_match = _draft_ref_re.search(text)
    ref_id = ref_match.group(1) if ref_match else None

    if not ref_id:
        # Also check recent messages for a "revise session draft [XXXX]" request
        recent = store.get_recent(count=20, channel=channel)
        for m in reversed(recent):
            m_text = m.get("text", "")
            if "revise session draft" in m_text.lower():
                ref_match = _draft_ref_re.search(m_text)
                if ref_match:
                    ref_id = ref_match.group(1)
                    break

    if ref_id:
        # Find the highest revision for this draft_id in existing messages
        max_rev = 0
        recent = store.get_recent(count=100, channel=channel)
        for m in recent:
            meta = m.get("metadata") or {}
            if meta.get("draft_id") == ref_id:
                max_rev = max(max_rev, meta.get("revision", 1))
        if max_rev > 0:
            return ref_id, max_rev + 1

    return str(uuid.uuid4())[:8], 1


async def _handle_new_message(msg: dict):
    """Broadcast message to web clients + check for @mention triggers."""
    # For broadcast slash commands, suppress the raw message — only the expanded
    # version should appear. Delete from store if it was persisted (MCP path),
    # and skip broadcasting the raw text.
    text = msg.get("text", "")
    msg_type = msg.get("type", "chat")
    sender = msg.get("sender", "")
    channel = msg.get("channel", "general")

    # Scranton: an agent can write to its DM before Lu ever opened it. Make the channel exist,
    # so the message shows up (Activity, badge, history) instead of sitting unseen in the log.
    if (channel.startswith("dm-") and channel not in room_settings.get("channels", [])
            and channel[3:] in (config or {}).get("agents", {}) and _CHANNEL_NAME_RE.match(channel)):
        room_settings["channels"].append(channel)
        _save_settings()
        await broadcast_settings()

    # Track last active channel for leave/join messages (skip system messages)
    global _last_active_channel
    if msg_type not in ("system", "leave", "join"):
        _last_active_channel = channel
        # Remember where this specific sender was last active so their
        # disconnect message follows them to the right channel.
        if sender and sender != "system":
            _agent_last_channel[sender] = channel
        # Scranton: "交 HH:MM" in an assignment → shown next to "X is working", PM told when it passes.
        try:
            if _sc_due_book().note(msg, set((config or {}).get("agents", {}).keys()),
                                   owner=str(room_settings.get("username") or "Lu")):
                await _broadcast_json({"type": "scranton_due", "items": _sc_due_book().public()})
        except Exception:
            _log_rate_limited("due note failed")
    # Strip @mentions to find the slash command (e.g. "@claude @codex /hatmaking")
    stripped = _re.sub(r"@[\w-]+\s*", "", text).strip().lower()
    _broadcast_cmds = ("/hatmaking", "/artchallenge", "/roastreview", "/poetry")
    cmd_word = stripped.split()[0] if stripped else ""
    is_broadcast_cmd = cmd_word in _broadcast_cmds
    known_agents = set(registry.get_all_names()) if registry else set()
    known_agents.update(config.get("agents", {}).keys())
    _session_draft_re = _re.compile(r'```session\s*\n(.*?)\n```', _re.DOTALL)
    draft_match = _session_draft_re.search(text)
    is_agent_session_draft = bool(draft_match and sender in known_agents)
    is_hidden_session_request = msg_type == "session_request"

    is_agent_continue = (stripped == "/continue" and sender in known_agents)
    suppress_broadcast = (
        is_broadcast_cmd
        or is_hidden_session_request
        or is_agent_session_draft
        or is_agent_continue
    )

    if not suppress_broadcast:
        await broadcast(msg)

    # If the raw slash command was persisted (MCP path), silently remove it.
    # It was never broadcast to WebSocket clients, so no delete event needed.
    if suppress_broadcast and msg.get("id"):
        store.delete([msg["id"]])

    # System messages never trigger routing - prevents infinite callback loops
    if sender == "system":
        return

    # Check for slash commands — use stripped text (sans @mentions)
    if stripped == "/continue":
        if sender in known_agents:
            store.add("system", f"Loop guard: only humans can /continue. {sender} tried to self-resume.", channel=channel)
            return
        router.continue_routing(channel)
        store.add("system", f"{sender} let the agents continue.", channel=channel)
        await broadcast_status()
        return

    if stripped == "/roastreview":
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        store.add(sender, f"{mentions} Time for a roast review! Inspect each other's work and constructively roast it.", channel=channel)
        return

    if stripped.startswith("/artchallenge"):
        parts = stripped.split(None, 1)
        theme = parts[1] if len(parts) > 1 else "anything you like"
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        store.add(
            sender,
            f"{mentions} Art challenge! Create an SVG artwork with the theme: **{theme}**. "
            "Write your SVG code to a .svg file, then attach it using chat_send(image_path=...). "
            "Make it creative, keep it under 5KB. Let's see what you've got!",
            channel=channel,
        )
        return

    if stripped == "/hatmaking":
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        all_instances = registry.get_all() if registry else {}
        agents_cfg = config.get("agents", {})
        color_parts = ", ".join(
            f"{a}={all_instances[a]['color']}" if a in all_instances
            else f"{a}={agents_cfg.get(a, {}).get('color', '#888')}"
            for a in agent_names
        )
        store.add(
            sender,
            f"{mentions} Hat making time! Design a new hat for your avatar using SVG. "
            "Use viewBox=\"0 0 32 16\" so it fits on top of a 32px avatar circle. "
            f"Background is dark (#0f0f17). Avatar colors: {color_parts}. Design for good contrast! "
            "Call chat_set_hat(sender=your_name, svg='<svg ...>...</svg>') to wear it. "
            "Be creative — top hats, party hats, crowns, propeller beanies, whatever you want!",
            channel=channel,
        )
        return

    if stripped.startswith("/poetry"):
        parts = stripped.split(None, 1)
        form = parts[1] if len(parts) > 1 else "haiku"
        if form not in ("haiku", "limerick", "sonnet"):
            form = "haiku"
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        prompts = {
            "haiku": "Write a haiku about the current state of this codebase.",
            "limerick": "Write a limerick about the current state of this codebase.",
            "sonnet": "Write a sonnet about the current state of this codebase.",
        }
        store.add(sender, f"{mentions} {prompts[form]}", channel=channel)
        return

    # Detect session draft blocks from agents only.
    # The session request prompt contains an example ```session block,
    # so treating every non-system sender as a draft source creates a false
    # invalid-draft card the moment the user asks for a custom session.
    _session_draft_re = _re.compile(r'```session\s*\n(.*?)\n```', _re.DOTALL)
    draft_match = _session_draft_re.search(text)
    known_agents = set(registry.get_all_names()) if registry else set()
    known_agents.update(config.get("agents", {}).keys())
    if draft_match and sender in known_agents:
        # Check if this is a revision of an existing draft
        draft_id, revision = _resolve_draft_lineage(text, channel)

        try:
            draft_json = json.loads(draft_match.group(1))
            errors = validate_session_template(draft_json)
            if errors:
                store.add(
                    "system",
                    f"Session draft from {sender} has errors:\n" + "\n".join(f"- {e}" for e in errors),
                    msg_type="session_draft",
                    channel=channel,
                    metadata={"draft_id": draft_id, "revision": revision, "proposed_by": sender,
                              "template": draft_json, "errors": errors, "valid": False},
                )
            else:
                draft_json.setdefault("id", f"draft-{draft_id}")
                store.add(
                    "system",
                    f"Session draft from {sender}: **{draft_json.get('name', '?')}**",
                    msg_type="session_draft",
                    channel=channel,
                    metadata={"draft_id": draft_id, "revision": revision, "proposed_by": sender,
                              "template": draft_json, "errors": [], "valid": True},
                )
        except json.JSONDecodeError:
            store.add(
                "system",
                f"Session draft from {sender} contains invalid JSON.",
                msg_type="session_draft",
                channel=channel,
                metadata={"draft_id": draft_id, "revision": revision, "proposed_by": sender,
                           "errors": ["Invalid JSON in session block"], "valid": False},
            )

    was_paused = router.is_paused(channel)
    raw_targets = router.get_targets(sender, text, channel)
    if router.is_paused(channel) != was_paused:
        await broadcast_status()   # paused by the loop guard, or a message from you let them go on
    # Scranton: a DM whose handle isn't a teammate would route nowhere silently.
    if (channel.startswith("dm-") and not raw_targets and msg_type == "chat"
            and sender.lower() == str(room_settings.get("username", "")).lower()
            and channel[3:] not in router.agent_names):
        store.add("system", f"Nobody received this: there's no teammate called @{channel[3:]}.",
                  msg_type="system", channel=channel)
    # Resolve base family names to actual registered instances
    # e.g. 'claude' → 'claude-prime' when slot-1 was renamed
    targets = []
    for t in raw_targets:
        if registry:
            targets.extend(registry.resolve_to_instances(t))
        else:
            targets.append(t)
    targets = list(dict.fromkeys(targets))  # dedupe, preserve order
    # Only the project manager @s Lu (Lu, 11-10). A teammate who opens with @Lu outside a DM
    # reaches the project manager instead: it isn't in Lu's Mentions, and the PM decides
    # whether it goes on her list.
    if _lu_ask_for_pm(sender, text, channel) and _mentions_from() not in targets:
        targets.append(_mentions_from())
    # ChatGPT plan running low (Agent Monitor's numbers): visual/motion work goes to the
    # Gemini interns instead (Lu, 11-10). DMs are left alone.
    targets, _quota_moved = _sc_quota.reroute(config, targets, channel, sender)
    if _quota_moved:
        pct = _sc_quota.status().get("percent")
        pairs = "、".join(f"{_label_of(a)} → {_label_of(b)}" for a, b in _quota_moved.items())
        store.add("system", f"转给 {pairs}（ChatGPT 额度 {pct:.0f}%）" if pct is not None else f"转给 {pairs}",
                  msg_type="system", channel=channel)

    if router.is_paused(channel):
        # Only emit the loop guard notice once per pause
        if not router.is_guard_emitted(channel):
            router.set_guard_emitted(channel)
            store.add(
                "system",
                f"The agents passed this back and forth {router.pause_hops(channel)} times, so I paused them. "
                "Type /continue to let them go on.",
                channel=channel
            )
        return

    # Build a readable message string for the wake prompt
    chat_msg = f"{sender}: {text}" if text else ""
    custom_prompt = text if is_hidden_session_request else ""

    # Session turn guard: if a session is active on this channel and the sender
    # is an agent, only allow triggering the agent whose turn it is.
    # Human @mentions are always allowed (the session engine handles pausing).
    sender_is_agent = sender in known_agents
    allowed_agent = session_engine.get_allowed_agent(channel) if session_engine and sender_is_agent else None

    # Scranton: if this message is a thread reply, woken agents answer in that thread.
    thread_root = _thread_root_of(msg, channel)

    for target in targets:
        # Session guard: suppress out-of-turn agent triggers
        if allowed_agent and target != allowed_agent:
            continue
        msg_for = chat_msg
        orig = next((a for a, b in _quota_moved.items() if b == target), "")
        if orig and chat_msg:
            msg_for = (f"{chat_msg}\n\n(Scranton: this was addressed to @{orig}; ChatGPT's plan is low, "
                       f"so it's yours. Read the thread for context and do it as @{orig} would.)")
        await _wake_teammate(target, msg_for, channel, custom_prompt, thread_root)


def _mentions_from() -> str:
    """[team] mentions_from: the one teammate whose @owner reaches the owner's Mentions
    ("" = anyone). Lu's own choice is "pm" (11-10); it's a setting, not a rule of Scranton."""
    return str((config or {}).get("team", {}).get("mentions_from", "") or "").strip().lower()


_LEAD_RE = _re.compile(r"^\s*(?:@[\w-]+[\s,，、]*)+")


def _lu_ask_for_pm(sender: str, text: str, channel: str) -> bool:
    """True when a teammate other than [team] mentions_from opens a channel message with @owner."""
    who = str(sender or "").lower()
    owner = str(room_settings.get("username", "") or "").lower()
    via = _mentions_from()
    if (not owner or not via or who in ("", "system", owner) or _re.sub(r"-\d+$", "", who) == via
            or str(channel or "").startswith("dm-")
            or via not in ((config or {}).get("agents") or {})):
        return False
    lead = _LEAD_RE.match(str(text or ""))
    if not lead:
        return False
    return bool(_re.search(r"(^|[^\w])@(" + _re.escape(owner) + r"|lu)(?![\w-])", lead.group(0), _re.I))


def _thread_root_of(msg: dict, channel: str):
    """The id of the thread this message is in (None if it's top level)."""
    thread_root = None
    try:
        rt = msg.get("reply_to")
        seen = set()
        while rt is not None and rt not in seen:
            seen.add(rt)
            parent = store.get_by_id(int(rt))
            if not parent or parent.get("channel", "general") != channel:
                break  # a thread never crosses channels
            thread_root = parent["id"]
            rt = parent.get("reply_to")
    except Exception:
        thread_root = None
    return thread_root



def _team_handles() -> set:
    """Teammates a message can be handed to (Grok Bot reads its own mentions, so it isn't one)."""
    return {str(a).lower() for a in (config or {}).get("agents", {})} - {_sc_grok.HANDLE}


def _is_humans_chat(m) -> bool:
    """A chat message you wrote (not a teammate's, the system's or Grok Bot's)."""
    if not m or m.get("type", "chat") != "chat":
        return False
    who = str(m.get("sender", "")).lower()
    agents_lc = {str(a).lower() for a in (config or {}).get("agents", {})}
    return not (who in agents_lc or who.rsplit("-", 1)[0] in agents_lc or who in ("system", "grok"))


def _added_mentions(old: str, new: str) -> list:
    """Teammates @-ed in the new text but not in the old one."""
    if not router:
        return []
    before = {m.lower() for m in router.parse_mentions(old or "")}
    after = [m.lower() for m in router.parse_mentions(new or "")]
    return sorted({m for m in after if m not in before} & _team_handles())

async def _wake_teammate(target: str, chat_msg: str, channel: str, custom_prompt: str = "", thread_root=None):
    """Hand one message to one teammate: start them if needed, add them to the channel, trigger."""
    import mcp_bridge
    if True:
        # Skip pending instances — they haven't been named/claimed yet
        if registry:
            inst = registry.get_instance(target)
            if inst and inst.get("state") == "pending":
                return
        if target == _sc_grok.HANDLE:
            return   # Grok Bot isn't a CLI here: it reads its mentions with `scranton.sh grok mentions`
        available = agents.is_available(target)
        if not available and target in (config or {}).get("agents", {}):
            # Scranton: @-ing a teammate who isn't running starts them; the message waits in
            # their queue (kept across the start), and they join this channel.
            res = await asyncio.to_thread(_scranton_ops.ensure_running, [target], config)
            if target in res.get("failed", {}):
                _report_start(res, channel, "mentioned")
                return
            if res.get("started"):
                _report_start(res, channel, "mentioned")
        elif not available:
            store.add("system", f"{target} isn't on the team, so nobody got this.", msg_type="system", channel=channel)
            return
        elif not mcp_bridge.is_online(target):
            store.add("system", f"{_label_of(target)} isn't running. They'll get this when they start.", msg_type="system", channel=channel)
        if not channel.startswith("dm-") and _add_members(channel, [target]):
            _save_settings()
            await broadcast_settings()
        await agents.trigger(target, message=chat_msg, channel=channel, prompt=custom_prompt,
                             thread=thread_root)


# --- broadcasting ---

async def _broadcast(raw_json: str):
    """Send a pre-serialized JSON string to all WebSocket clients."""
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(raw_json)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast(msg: dict):
    data = json.dumps({"type": "message", "data": msg})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_status():
    status = agents.get_status()
    paused = [ch for ch in room_settings.get("channels", ["general"]) if router.is_paused(ch)]
    status["paused"] = bool(paused)
    status["paused_channels"] = paused   # Scranton: the page shows the pause card only where it's true
    data = json.dumps({"type": "status", "data": status})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_typing(agent_name: str, is_typing: bool):
    data = json.dumps({"type": "typing", "agent": agent_name, "active": is_typing})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_clear(channel: str | None = None):
    payload = {"type": "clear"}
    if channel:
        payload["channel"] = channel
    data = json.dumps(payload)
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_todo_update(msg_id: int, status: str | None):
    data = json.dumps({"type": "todo_update", "data": {"id": msg_id, "status": status}})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_settings():
    data = json.dumps({"type": "settings", "data": room_settings})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_rule(action: str, rule: dict):
    data = json.dumps({"type": "rule", "action": action, "data": rule})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_job(action: str, data: dict):
    payload = json.dumps({"type": "job", "action": action, "data": data})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_schedule(action: str, schedule: dict):
    payload = json.dumps({"type": "schedule", "action": action, "data": schedule})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_session(action: str, session: dict):
    payload = json.dumps({"type": "session", "action": action, "data": session})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_hats():
    data = json.dumps({"type": "hats", "data": agent_hats})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_agents():
    """Send updated agent config (from registry) to all WebSocket clients."""
    agent_cfg = registry.get_agent_config() if registry else {}
    data = json.dumps({"type": "agents", "data": agent_cfg})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


def _on_registry_change():
    """Called from registry (any thread) when instances register/deregister/claim/rename."""
    # Update router with current agent names (base names + registered instances)
    if router and registry:
        base_names = list(registry.get_bases().keys())
        # Only include active instances in routing (pending ones are inert)
        instance_names = registry.get_active_names()
        all_names = list(set(base_names + instance_names))
        router.update_agents(all_names)
    # Broadcast to WebSocket clients
    if _event_loop:
        asyncio.run_coroutine_threadsafe(broadcast_agents(), _event_loop)
        asyncio.run_coroutine_threadsafe(broadcast_status(), _event_loop)


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # --- Security: validate session token on WebSocket connect ---
    token = websocket.query_params.get("token", "")
    # Scranton: browsers always send Origin on WebSockets; only our own pages may connect.
    ws_origin = getattr(websocket, "headers", {}).get("origin")
    if ws_origin and ws_origin.rstrip("/") not in getattr(sys.modules[__name__], "allowed_ws_origins", set()):
        token = ""  # fall through to the same rejection as a bad token
    if token != session_token:
        # Must accept before closing so the browser receives the close frame.
        # Code 4003 triggers an auto-reload in the client to pick up the new token.
        await websocket.accept()
        await websocket.close(code=4003, reason="forbidden: invalid session token")
        return

    await websocket.accept()
    ws_clients.add(websocket)

    # Send settings
    await websocket.send_text(json.dumps({"type": "settings", "data": room_settings}))

    # Send registered instances (used for pills/mentions)
    agent_cfg = registry.get_agent_config() if registry else {}
    await websocket.send_text(json.dumps({"type": "agents", "data": agent_cfg}))

    # Send base agent colors (used for message coloring, no pills)
    base_colors = {}
    for name, cfg in config.get("agents", {}).items():
        base_colors[name] = {"color": cfg.get("color", "#888"), "label": cfg.get("label", name)}
    await websocket.send_text(json.dumps({"type": "base_colors", "data": base_colors}))

    # Send todos {msg_id: status}
    await websocket.send_text(json.dumps({"type": "todos", "data": store.get_todos()}))

    # Send rules
    await websocket.send_text(json.dumps({"type": "rules", "data": rules.list_all()}))

    # Send hats
    await websocket.send_text(json.dumps({"type": "hats", "data": agent_hats}))

    # Send jobs
    await websocket.send_text(json.dumps({"type": "jobs", "data": jobs.list_all()}))

    # Send schedules
    await websocket.send_text(json.dumps({"type": "schedules", "data": schedules.list_all()}))

    # Send pending instances (so late-connecting browsers still see the naming lightbox)
    if registry:
        for inst in registry.get_all().values():
            if inst.get("state") == "pending":
                await websocket.send_text(json.dumps({
                    "type": "pending_instance",
                    "name": inst["name"],
                    "base": inst.get("base", ""),
                    "label": inst.get("label", inst["name"]),
                    "color": inst.get("color", "#888"),
                }))

    # Send history (per channel based on history_limit)
    limit_val = room_settings.get("history_limit", "all")
    # Scranton: "all" meant 10,000 per channel, sent and rendered on every page load and
    # every reconnect (18 MB at 30k messages). The newest 1,000 per channel is plenty to read;
    # search still covers everything.
    count = HISTORY_CAP if limit_val == "all" else min(int(limit_val), HISTORY_CAP)
    
    # Scranton (Lu, 11-10: phone and Mac app took ~5 s to open): the page opens with the newest
    # INITIAL_HISTORY per channel; scrolling up loads the rest, and Activity gets its own list
    # (/api/scranton/inbox-feed), so nothing that needs Lu is missed.
    count = min(count, INITIAL_HISTORY)
    history = []
    for ch in room_settings["channels"]:
        history.extend(store.get_recent(count, channel=ch))
    # A thread whose first message is older than that still shows where it started.
    have = {m.get("id") for m in history}
    for m in list(history):
        rt, hops = m.get("reply_to"), 0
        while rt is not None and rt not in have and hops < 20:
            root = store.get_by_id(int(rt))
            if not root:
                break
            have.add(root["id"])
            history.append({**root, "_extra": True})
            rt, hops = root.get("reply_to"), hops + 1
    
    # Sort history by timestamp to interleave messages from different channels correctly
    history.sort(key=lambda m: m.get("timestamp", 0))
    
    # Saved messages have their own boundary; presence updates can arrive at
    # any time and must never make old history look like new chat.
    for offset in range(0, len(history), 100):
        await websocket.send_text(json.dumps({
            "type": "history", "messages": history[offset:offset + 100],
        }))
        await asyncio.sleep(0)
    await websocket.send_text(json.dumps({"type": "history_complete"}))

    # Send status
    await broadcast_status()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue   # a stray "null" must not close the connection (sending would then fail)

            if event.get("type") == "message":
                text = event.get("text", "").strip()
                attachments = event.get("attachments", [])
                sender = event.get("sender") or room_settings.get("username", "user")
                channel = event.get("channel", "general")
                # Scranton: a stale view (renamed/deleted channel) must not store
                # messages where no list shows them.
                if channel not in room_settings.get("channels", ["general"]):
                    channel = "general"

                if not text and not attachments:
                    continue

                # Command handling
                if text.startswith("/"):
                    cmd_parts = text.split()
                    cmd = cmd_parts[0].lower()
                    if cmd == "/clear":
                        store.clear(channel=channel)
                        await broadcast_clear(channel=channel)
                        continue
                    if cmd == "/continue":
                        # Resume the channel it was typed in (no argument resumed #general),
                        # and say so: the command itself isn't stored as a message.
                        router.continue_routing(channel)
                        store.add("system", f"{_label_of(sender)} let the agents continue.", channel=channel)
                        await broadcast_status()
                        continue
                    # Broadcast slash commands — expand without storing the raw command.
                    # _handle_new_message will store the expanded version.
                    if cmd in ("/hatmaking", "/artchallenge", "/roastreview", "/poetry"):
                        await _handle_new_message({"sender": sender, "text": text, "channel": channel})
                        continue

                # Store message — the on_message callback handles broadcast + triggers
                reply_to = event.get("reply_to")
                if reply_to is not None:
                    reply_to = int(reply_to)

                # Scranton: a message sent on your behalf by another tool (a Claude session) keeps
                # your name but says so: "via Claude" (Lu, 11-09, 4B).
                via = str(event.get("via") or "").strip().lower()
                meta = {"via": via} if _VIA_RE.fullmatch(via or "") else None
                store.add(sender, text, attachments=attachments, reply_to=reply_to,
                          channel=channel, metadata=meta)

            elif event.get("type") == "react":
                # Scranton: toggle an emoji reaction by the human on a message.
                try:
                    mid = int(event.get("id"))
                except (TypeError, ValueError):
                    continue
                emoji = str(event.get("emoji") or "")[:16]
                if not emoji or any(c.isspace() for c in emoji):
                    continue
                target = store.get_by_id(mid)
                if not target:
                    continue
                who = room_settings.get("username", "user")
                reactions = {k: list(v) for k, v in (target.get("reactions") or {}).items()}
                users = reactions.get(emoji, [])
                if who in users:
                    users.remove(who)
                else:
                    users.append(who)
                if users:
                    reactions[emoji] = users
                else:
                    reactions.pop(emoji, None)
                if len(reactions) > 20:
                    continue
                store.update_message(mid, {"reactions": reactions})
                await _broadcast(json.dumps({"type": "reaction", "id": mid, "reactions": reactions}))
                continue

            elif event.get("type") == "delete":
                ids = event.get("ids", [])
                if ids:
                    # Scranton: deleting a thread's first message takes its replies with it, so
                    # they don't linger in search with nothing to open.
                    want = {int(i) for i in ids}
                    grew = True
                    while grew:
                        extra = {m["id"] for m in store.get_since(-1)
                                 if m.get("reply_to") is not None and int(m["reply_to"]) in want and m["id"] not in want}
                        grew = bool(extra)
                        want |= extra
                    deleted = store.delete(sorted(want))
                    if deleted:
                        data = json.dumps({"type": "delete", "ids": deleted})
                        dead = set()
                        for client in list(ws_clients):
                            try:
                                await client.send_text(data)
                            except Exception:
                                dead.add(client)
                        ws_clients.difference_update(dead)
                continue

            elif event.get("type") == "edit_text":
                # Scranton: fix a typo in your own message. Agents already got the original, so
                # an edit doesn't wake anyone again; the message shows "edited".
                try:
                    mid = int(event.get("id"))
                except (TypeError, ValueError):
                    continue
                text = str(event.get("text") or "").strip()
                if not text or len(text) > 20000:
                    continue
                cur = store.get_by_id(mid)
                if not _is_humans_chat(cur):
                    continue   # only your own chat messages
                if text == cur.get("text"):
                    continue
                # Teammates the edit @s for the first time never got this message: the page offers
                # to send it to them (Lu, 11-09). Nobody is woken without that click.
                added = _added_mentions(cur.get("text", ""), text)
                import time as _tedit
                updated = store.update_message(mid, {"text": text, "edited": _tedit.time()})
                if updated:
                    payload = json.dumps({"type": "edit", "message": updated, "added_mentions": added})
                    for client in list(ws_clients):
                        try:
                            await client.send_text(payload)
                        except Exception:
                            pass
                continue

            elif event.get("type") == "edit_resend":
                # Scranton: after an edit added @someone, you chose to send the edited message to them.
                try:
                    mid = int(event.get("id"))
                except (TypeError, ValueError):
                    continue
                cur = store.get_by_id(mid)
                if not _is_humans_chat(cur):
                    continue
                mentioned = {m.lower() for m in router.parse_mentions(cur.get("text", ""))} if router else set()
                to = [str(t).lower() for t in (event.get("to") or []) if isinstance(t, str)]
                to = [t for t in dict.fromkeys(to) if t in mentioned and t in _team_handles()]
                if not to:
                    continue
                ch = cur.get("channel", "general")
                root = _thread_root_of(cur, ch)
                note = f"{cur.get('sender')} (edited this message and added you): {cur.get('text', '')}"
                for t in to:
                    await _wake_teammate(t, note, ch, "", root)
                store.add("system", "Sent the edited message to " + ", ".join(_label_of(t) for t in to) + ".",
                          msg_type="system", channel=ch, reply_to=root)
                continue

            elif event.get("type") == "todo_add":
                msg_id = event.get("id")
                if msg_id is not None:
                    store.add_todo(int(msg_id))
                    await broadcast_todo_update(int(msg_id), "todo")
                continue

            elif event.get("type") == "todo_toggle":
                msg_id = event.get("id")
                if msg_id is not None:
                    mid = int(msg_id)
                    status = store.get_todo_status(mid)
                    if status == "todo":
                        store.complete_todo(mid)
                        await broadcast_todo_update(mid, "done")
                    elif status == "done":
                        store.reopen_todo(mid)
                        await broadcast_todo_update(mid, "todo")
                continue

            elif event.get("type") == "todo_remove":
                msg_id = event.get("id")
                if msg_id is not None:
                    store.remove_todo(int(msg_id))
                    await broadcast_todo_update(int(msg_id), None)
                continue

            elif event.get("type") in ("decision_propose", "rule_propose"):
                text = event.get("text") or event.get("decision", "")
                text = text.strip()
                author = event.get("author") or event.get("owner") or room_settings.get("username", "user")
                reason = event.get("reason", "")
                is_human = author.lower() == room_settings.get("username", "user").lower()
                if text:
                    rule = rules.propose(text, author, reason)
                    if rule:
                        if is_human:
                            # Human-created rules go straight to draft, no card
                            rules.make_draft(rule["id"])
                        else:
                            # Agent proposals get a card in the timeline
                            channel = event.get("channel", "general")
                            msg = store.add(
                                author, f"Rule proposal: {text}",
                                msg_type="rule_proposal",
                                channel=channel,
                                metadata={"rule_id": rule["id"], "text": text, "status": "pending"},
                            )
                            # store.add() fires _on_store_message → broadcast already.
                            # Do NOT call broadcast(msg) again here.
                continue

            elif event.get("type") in ("decision_approve", "rule_activate"):
                rid = event.get("id")
                if rid is not None:
                    if not rules.activate(int(rid)):
                        await websocket.send_text(json.dumps({
                            "type": "rule_error", "error": "Rule no longer exists. Refresh the page.",
                        }))
                continue

            elif event.get("type") in ("decision_unapprove", "rule_deactivate"):
                rid = event.get("id")
                if rid is not None:
                    rules.deactivate(int(rid))
                continue

            elif event.get("type") == "rule_make_draft":
                rid = event.get("id")
                if rid is not None:
                    rules.make_draft(int(rid))
                continue

            elif event.get("type") in ("decision_edit", "rule_edit"):
                rid = event.get("id")
                if rid is not None:
                    rules.edit(
                        int(rid),
                        text=event.get("text") or event.get("decision"),
                        reason=event.get("reason"),
                    )
                continue

            elif event.get("type") in ("decision_delete", "rule_delete"):
                rid = event.get("id")
                if rid is not None:
                    rules.delete(int(rid))
                continue

            elif event.get("type") == "rule_remind":
                rules.set_remind()
                remind_data = json.dumps({"type": "rules_remind", "data": {}})
                for client in list(ws_clients):
                    try:
                        await client.send_text(remind_data)
                    except Exception:
                        pass
                continue

            elif event.get("type") == "update_settings":
                new = event.get("data", {})
                if "title" in new and isinstance(new["title"], str):
                    room_settings["title"] = new["title"].strip() or "Scranton"
                apply_room_subtitle(new)
                if "username" in new and isinstance(new["username"], str):
                    old_user = room_settings.get("username", "user")
                    new_user = new["username"].strip()[:20] or "user"
                    agent_names = {n.lower() for n in (config or {}).get("agents", {})} | {
                        str(a.get("label", "")).lower() for a in (config or {}).get("agents", {}).values()}
                    if new_user.lower() in agent_names:
                        new_user = old_user   # Scranton: can't take an agent's name
                    room_settings["username"] = new_user
                    if new_user != old_user and old_user != "user":
                        # Scranton: your past messages are still yours under the new name.
                        moved = await asyncio.to_thread(store.rename_sender, old_user, new_user)
                        if moved:
                            for c in list(ws_clients):
                                try:
                                    await c.send_text(json.dumps({"type": "scranton_reload", "reason": "renamed"}))
                                except Exception:
                                    pass
                if "font" in new and new["font"] in ("mono", "serif", "sans"):
                    room_settings["font"] = new["font"]
                if "max_agent_hops" in new:
                    try:
                        hops = int(new["max_agent_hops"])
                        hops = max(1, min(hops, 50))
                        room_settings["max_agent_hops"] = hops
                        router.max_hops = hops
                    except (ValueError, TypeError):
                        pass
                if "contrast" in new and new["contrast"] in ("normal", "high"):
                    room_settings["contrast"] = new["contrast"]
                if "rules_refresh_interval" in new:
                    try:
                        ri = int(new["rules_refresh_interval"])
                        room_settings["rules_refresh_interval"] = max(0, min(ri, 100))
                    except (ValueError, TypeError):
                        pass
                if "history_limit" in new:
                    val = str(new["history_limit"]).strip().lower()
                    if val == "all":
                        room_settings["history_limit"] = "all"
                    else:
                        try:
                            val_int = int(val)
                            room_settings["history_limit"] = max(1, min(val_int, 10000))
                        except (ValueError, TypeError):
                            pass
                if "custom_roles" in new and isinstance(new["custom_roles"], list):
                    room_settings["custom_roles"] = [
                        str(r).strip()[:20] for r in new["custom_roles"]
                        if isinstance(r, str) and r.strip()
                    ][:20]
                _save_settings()
                await broadcast_settings()

            elif event.get("type") == "rename_agent":
                agent_name = (event.get("name") or "").strip()
                new_label = (event.get("label") or "").strip()
                if agent_name and new_label and registry:
                    # Derive a sanitized sender ID from the label
                    import re as _re
                    new_id = _re.sub(r'[^a-z0-9-]', '', new_label.lower().replace(' ', '-')).strip('-')
                    if not new_id:
                        new_id = agent_name  # fallback: keep old name, just change label
                    if new_id == agent_name:
                        # Same ID — label-only change
                        registry.set_label(agent_name, new_label)
                    else:
                        result = registry.rename(agent_name, new_id, new_label)
                        if isinstance(result, str):
                            # Rename failed (collision etc.) — fall back to label-only
                            registry.set_label(agent_name, new_label)
                        else:
                            # Migrate presence + cursors to new name
                            import mcp_bridge
                            mcp_bridge.migrate_identity(agent_name, new_id)
                            # Update sender on all historical messages
                            store.rename_sender(agent_name, new_id)
                            _migrate_agent_last_channel(agent_name, new_id)
                            # Notify clients so they can update sender in DOM
                            rename_event = json.dumps({
                                "type": "agent_renamed",
                                "old_name": agent_name,
                                "new_name": new_id,
                            })
                            await _broadcast(rename_event)
                continue

            elif event.get("type") == "name_pending":
                # Human names a pending instance (from lightbox)
                agent_name = (event.get("name") or "").strip()
                new_label = (event.get("label") or "").strip()
                if agent_name and registry:
                    if not new_label:
                        # Accept default name
                        registry.confirm_pending(agent_name)
                    else:
                        import re as _re
                        new_id = _re.sub(r'[^a-z0-9-]', '', new_label.lower().replace(' ', '-')).strip('-')
                        if not new_id:
                            new_id = agent_name
                        if new_id == agent_name:
                            # Same ID — just update label and confirm
                            registry.set_label(agent_name, new_label)
                            registry.confirm_pending(agent_name)
                        else:
                            result = registry.rename(agent_name, new_id, new_label)
                            if isinstance(result, str):
                                # Rename failed — just confirm with label
                                registry.set_label(agent_name, new_label)
                                registry.confirm_pending(agent_name)
                            else:
                                # Rename succeeded — confirm new name
                                registry.confirm_pending(new_id)
                                import mcp_bridge
                                mcp_bridge.migrate_identity(agent_name, new_id)
                                # Update sender on all historical messages
                                store.rename_sender(agent_name, new_id)
                                _migrate_agent_last_channel(agent_name, new_id)
                                rename_event = json.dumps({
                                    "type": "agent_renamed",
                                    "old_name": agent_name,
                                    "new_name": new_id,
                                })
                                await _broadcast(rename_event)
                continue

            elif event.get("type") == "channel_create":
                name = (event.get("name") or "").strip().lower()
                # Scranton: dm-<handle> is reserved for direct messages with a configured teammate.
                if name.startswith("dm-") and name[3:] not in (config or {}).get("agents", {}):
                    continue
                if not name or not _CHANNEL_NAME_RE.match(name):
                    continue
                if name in room_settings["channels"]:
                    continue
                room_settings["channels"].append(name)
                _save_settings()
                await broadcast_settings()

            elif event.get("type") == "members_update":
                # Scranton: add / remove teammates in a channel. Added ones are started if needed.
                ch = (event.get("channel") or "").strip().lower()
                if ch not in room_settings["channels"] or ch.startswith("dm-"):
                    continue
                add = [str(n).strip().lower() for n in (event.get("add") or [])][:30]
                remove = {str(n).strip().lower() for n in (event.get("remove") or [])}
                added = _add_members(ch, add)
                if remove:
                    room_settings.setdefault("channel_members", {})[ch] = [
                        n for n in _channel_members(ch) if n not in remove]
                _save_settings()
                await broadcast_settings()
                to_start = [n for n in added if not agents.is_available(n)]   # already connected: leave it
                if to_start:
                    res = await asyncio.to_thread(_scranton_ops.ensure_running, to_start, config)
                    _report_start(res, ch, "added to the channel")

            elif event.get("type") == "start_agents":
                # Scranton: the "Start" buttons (DM header, channel member list)
                names = [str(n).strip().lower() for n in (event.get("names") or [])][:30]
                ch = (event.get("channel") or "general").strip().lower()
                if ch not in room_settings["channels"]:
                    ch = "general"
                to_start = [n for n in names if n in (config or {}).get("agents", {}) and not agents.is_available(n)]
                if to_start:
                    res = await asyncio.to_thread(_scranton_ops.ensure_running, to_start, config)
                    _report_start(res, ch, "started from the page")

            elif event.get("type") == "channel_reorder":
                # Scranton: drag channels (or Alt+↑/↓) to reorder. Same set of names, new order.
                # The sidebar only lists some of them (DMs live in their own list), so the order
                # covers a subset: those take each other's places, the rest stay put. (It used to
                # need every name, so dragging silently did nothing once a DM existed.)
                order = [str(n).strip().lower() for n in (event.get("order") or [])]
                cur = list(room_settings["channels"])
                if order and len(set(order)) == len(order) and set(order) <= set(cur):
                    it = iter(order)
                    new = [next(it) if c in set(order) else c for c in cur]
                    if new != cur:
                        room_settings["channels"] = new
                        _save_settings()
                        await broadcast_settings()

            elif event.get("type") == "channel_rename":
                old_name = (event.get("old_name") or "").strip().lower()
                new_name = (event.get("new_name") or "").strip().lower()
                if old_name.startswith("dm-") or new_name.startswith("dm-"):
                    continue  # Scranton: DM channels can't be renamed, and dm- names are reserved
                if old_name == "general":
                    continue
                if not new_name or not _CHANNEL_NAME_RE.match(new_name):
                    continue
                if old_name not in room_settings["channels"]:
                    continue
                if new_name in room_settings["channels"]:
                    continue
                idx = room_settings["channels"].index(old_name)
                room_settings["channels"][idx] = new_name
                cm = room_settings.get("channel_members") or {}
                if old_name in cm:
                    cm[new_name] = cm.pop(old_name)
                meta = room_settings.get("channel_meta") or {}
                if old_name in meta:
                    meta[new_name] = meta.pop(old_name)
                store.rename_channel(old_name, new_name)
                import mcp_bridge
                mcp_bridge.migrate_cursors_rename(old_name, new_name)
                _save_settings()
                # Tell clients to migrate DOM elements. Scranton: before the new settings, so a tab
                # viewing the old name follows it instead of falling back to #general.
                rename_event = json.dumps({
                    "type": "channel_renamed",
                    "old_name": old_name,
                    "new_name": new_name,
                })
                for c in list(ws_clients):
                    try:
                        await c.send_text(rename_event)
                    except Exception:
                        pass
                await broadcast_settings()

            elif event.get("type") == "channel_delete":
                name = (event.get("name") or "").strip().lower()
                if name == "general":
                    continue
                if name not in room_settings["channels"]:
                    continue
                room_settings["channels"].remove(name)
                (room_settings.get("channel_members") or {}).pop(name, None)
                (room_settings.get("channel_meta") or {}).pop(name, None)
                store.delete_channel(name)
                import mcp_bridge
                mcp_bridge.migrate_cursors_delete(name)
                _save_settings()
                await broadcast_settings()

    except WebSocketDisconnect:
        ws_clients.discard(websocket)
    except Exception:
        ws_clients.discard(websocket)
        log.exception("WebSocket error")


# --- REST endpoints ---

IMAGE_UPLOAD_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
ALLOWED_UPLOAD_EXTS = IMAGE_UPLOAD_EXTS  # backwards-compatible image policy
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB default


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...), display_name: str | None = Form(None)):
    upload_dir = Path(config.get("images", {}).get("upload_dir", "./uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Uploaded names are display labels only; never use them as disk paths.
    name = (display_name or file.filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
    ext = Path(name).suffix.lower()
    file_cfg = config.get("attachments", {})
    allowed_files = {str(value).lower() for value in file_cfg.get("allowed_extensions", ["*"])}
    is_image = ext in IMAGE_UPLOAD_EXTS
    if not is_image and "*" not in allowed_files and ext not in allowed_files:
        return JSONResponse({"error": f"unsupported file type: {ext or '(no extension)'}"}, status_code=400)

    policy = config.get("images", {}) if is_image else file_cfg
    max_mb = policy.get("max_size_mb", 10 if is_image else 25)
    max_bytes = int(max_mb * 1024 * 1024)
    # Keep storage URLs simple even for names with unusual suffixes (e.g. .c++).
    storage_ext = ext if not ext or _re.fullmatch(r"\.[a-z0-9_-]{1,32}", ext) else ".bin"
    filename = f"{uuid.uuid4().hex}{storage_ext}"
    filepath = upload_dir / filename
    size = 0
    try:
        with filepath.open("xb") as destination:
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"file too large (max {max_mb} MB)")
                destination.write(chunk)
    except ValueError as exc:
        filepath.unlink(missing_ok=True)
        return JSONResponse({"error": str(exc)}, status_code=413)
    except BaseException:
        filepath.unlink(missing_ok=True)
        raise

    import mimetypes

    return JSONResponse({
        "name": name,
        "url": f"/uploads/{filename}",
        "size": size,
        "media_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
        "kind": "image" if is_image else "file",
    })


# --- Export / Import ---

@app.get("/api/export")
async def export_history():
    """Download a zip archive of project history."""
    import archive as _archive
    import time as _time
    try:
        zip_bytes = _archive.build_export(
            store, jobs, rules, summaries,
            app_version=config.get("server", {}).get("version", ""),
        )
    except Exception as exc:
        return JSONResponse({"error": f"export failed: {exc}"}, status_code=500)
    filename = f"agentchattr-export-{_time.strftime('%Y%m%d-%H%M%S')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/import")
async def import_history(file: UploadFile = File(...)):
    """Upload a zip archive and merge it into current stores."""
    import archive as _archive
    if not file.filename or not file.filename.lower().endswith(".zip"):
        return JSONResponse({"error": "unsupported file type: expected .zip"}, status_code=400)
    content = await file.read()
    if len(content) > _archive.MAX_IMPORT_SIZE:
        return JSONResponse(
            {"error": f"file too large (max {_archive.MAX_IMPORT_SIZE // 1024 // 1024}MB)"},
            status_code=400,
        )
    channel_list = list(room_settings.get("channels", ["general"]))
    max_ch = room_settings.get("max_channels", 8)
    report = _archive.import_archive(
        content, store, jobs, rules, summaries,
        channel_list, max_channels=max_ch,
    )
    if not report.get("ok"):
        error = report.get("error", "import failed")
        status = 409 if "already running" in error else 400
        return JSONResponse({"error": error}, status_code=status)
    # Update channel list if new channels were created
    if report["channels"]["created"]:
        room_settings["channels"] = channel_list
        _save_settings()
        await broadcast_settings()
    # Tell all connected clients to reload (picks up imported messages)
    data = json.dumps({"type": "reload"})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)
    return JSONResponse(report)


@app.get("/api/messages")
async def get_messages(since_id: int = 0, limit: int = 50, channel: str = ""):
    ch = channel if channel else None
    if since_id:
        return store.get_since(since_id, channel=ch)
    return store.get_recent(limit, channel=ch)


@app.post("/api/send")
async def api_send(request: Request):
    """REST endpoint for API agents to send messages without WebSocket.

    Authenticated via Bearer registration token. Sender is resolved from
    the token — the agent cannot impersonate another identity.
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return JSONResponse({"error": "missing Authorization: Bearer <token>"}, status_code=401)
    token = auth[7:].strip()
    inst = registry.resolve_token(token) if registry else None
    if not inst:
        return JSONResponse({"error": "invalid or expired token"}, status_code=403)

    sender = inst["name"]
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    channel = body.get("channel", "general")

    reply_to = body.get("reply_to")
    try:
        reply_to = int(reply_to) if reply_to is not None else None
    except (TypeError, ValueError):
        reply_to = None
    msg = store.add(sender, text, channel=channel, reply_to=reply_to)
    return JSONResponse(msg)


@app.get("/api/status")
async def get_status():
    status = agents.get_status()
    status["paused"] = any(router.is_paused(ch) for ch in room_settings.get("channels", ["general"]))
    return status


@app.get("/api/settings")
async def get_settings():
    return room_settings


@app.delete("/api/hat/{agent_name}")
async def delete_hat(agent_name: str):
    """Remove an agent's hat (called by the trash-can UI)."""
    clear_agent_hat(agent_name)
    return JSONResponse({"ok": True})


# --- Jobs API ---

@app.get("/api/schedules")
async def get_schedules():
    return schedules.list_all()


@app.post("/api/schedules")
async def create_schedule(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    targets = body.get("targets", [])
    channel = body.get("channel", "general")
    spec = body.get("spec", "")
    one_shot = bool(body.get("one_shot", False))
    send_at_date = body.get("send_at_date", "")  # "YYYY-MM-DD" for one-shot
    created_by = body.get("created_by", "user")
    if not prompt or not targets or not spec:
        return JSONResponse({"error": "prompt, targets, and spec are required"}, status_code=400)
    # A relative send ("in 2h 30m") is resolved by the client, which posts the
    # resulting moment directly; there is no recurrence to parse out of it.
    # A send_at names a single moment, so it only means anything for a one-shot.
    # A recurring request ignores it, exactly as it did before the field
    # existed; that keeps an unparseable spec falling through to the 400 below
    # instead of being stored as an unasked-for daily repeat.
    explicit_send_at = None
    if one_shot and body.get("send_at") is not None:
        try:
            explicit_send_at = float(body["send_at"])
        except (TypeError, ValueError, OverflowError):
            return JSONResponse(
                {"error": "send_at must be an epoch timestamp"}, status_code=400
            )
    interval_sec, daily_at = parse_schedule_spec(spec)
    if interval_sec is None and explicit_send_at is None:
        return JSONResponse({"error": f"Invalid schedule spec: {spec}"}, status_code=400)
    # For one-shot, compute exact send_at timestamp from date + daily_at time
    send_at = explicit_send_at
    if send_at is None and one_shot and daily_at and send_at_date:
        import datetime as _dt
        try:
            dt = _dt.datetime.strptime(f"{send_at_date} {daily_at}", "%Y-%m-%d %H:%M")
            send_at = dt.timestamp()
        except ValueError:
            pass
    try:
        s = schedules.create(
            prompt=prompt, targets=targets, channel=channel,
            interval_seconds=interval_sec, daily_at=daily_at,
            one_shot=one_shot, send_at=send_at,
            created_by=created_by,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(s)


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    removed = schedules.delete(schedule_id)
    if not removed:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


@app.patch("/api/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str):
    result = schedules.toggle(schedule_id)
    if not result:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(result)


@app.get("/api/jobs")
async def get_jobs(channel: str = "", status: str = ""):
    """List jobs, optionally filtered."""
    ch = channel if channel else None
    st = status if status else None
    return jobs.list_all(channel=ch, status=st)


@app.post("/api/messages/{msg_id}/demote")
async def demote_proposal(msg_id: int):
    """Demote a proposal-style message back to a regular chat message."""
    msg = store.get_by_id(msg_id)
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    msg_type = msg.get("type")
    if msg_type not in {"job_proposal", "session_draft"}:
        return JSONResponse({"error": "not a proposal"}, status_code=400)
    meta = msg.get("metadata", {})
    updated_fields = {"type": "chat", "metadata": {}}

    if msg_type == "job_proposal":
        body_text = meta.get("body", "")
        title = meta.get("title", "")
        plain_text = f"**{title}**\n\n{body_text}" if title else body_text or msg.get("text", "")
        updated_fields["text"] = plain_text
    else:
        tmpl = meta.get("template")
        errors = meta.get("errors", []) or []
        proposed_by = meta.get("proposed_by") or msg.get("sender", "system")
        parts = []

        if isinstance(tmpl, dict):
            name = str(tmpl.get("name", "")).strip()
            desc = str(tmpl.get("description", "")).strip()
            if name:
                parts.append(f"**{name}**")
            if desc:
                parts.append(desc)
            phases = tmpl.get("phases") or []
            if phases:
                lines = []
                for i, ph in enumerate(phases, 1):
                    ph_name = ph.get("name", f"Round {i}")
                    participants = ", ".join(ph.get("participants", []))
                    line = f"{i}. {ph_name}"
                    if participants:
                        line += f" -- {participants}"
                    prompt = (ph.get("prompt") or "").strip()
                    if prompt:
                        line += f"\n   {prompt}"
                    lines.append(line)
                parts.append("\n".join(lines))
        else:
            label = str(msg.get("text", "")).strip() or "Session draft"
            parts.append(label)
            if errors:
                parts.append("\n".join(f"- {e}" for e in errors))

        updated_fields["sender"] = proposed_by
        updated_fields["text"] = "\n\n".join(p for p in parts if p).strip()

    updated = store.update_message(msg_id, updated_fields)
    if updated:
        # Broadcast the updated message to all clients
        payload = json.dumps({"type": "edit", "message": updated})
        dead = set()
        for client in list(ws_clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.add(client)
        ws_clients.difference_update(dead)
    return updated or {"ok": True}


@app.post("/api/messages/{msg_id}/resolve_decision")
async def resolve_decision(msg_id: int, request: Request):
    """Resolve an inline decision card by recording the chosen option."""
    body = await request.json()
    chosen = str(body.get("choice", "") or "").strip()[:500]
    other = bool(body.get("other"))   # typed in the card's "Something else" row
    if not chosen:
        return JSONResponse({"error": "choice is required"}, status_code=400)
    # Atomic check + resolve under lock to prevent double-click race
    error = None
    channel = "general"
    sender = ""
    with store._lock:
        msg = None
        for m in store._messages:
            if m["id"] == msg_id:
                msg = m
                break
        if not msg:
            error = ("message not found", 404)
        elif msg.get("type") != "decision":
            error = ("not a decision message", 400)
        else:
            meta = msg.get("metadata") or {}
            if meta.get("resolved"):
                error = ("already resolved", 400)
            else:
                valid_choices = meta.get("choices", [])
                if valid_choices and not other and chosen not in valid_choices:
                    error = (f"invalid choice. Valid: {valid_choices}", 400)
                else:
                    meta["resolved"] = True
                    meta["chosen"] = chosen
                    if other:
                        meta["other"] = True
                    msg["metadata"] = meta
                    channel = msg.get("channel", "general")
                    sender = msg.get("sender", "")
                    store._rewrite()
    if error:
        return JSONResponse({"error": error[0]}, status_code=error[1])
    # Post the chosen answer as a regular chat message tagged @sender
    username = room_settings.get("username", "user")
    # Same shape as clicking an "A. …" option card: "@pm B：text" (the letter tells which row).
    _opts = list((msg or {}).get("metadata", {}).get("choices") or [])
    _letter = chr(65 + (len(_opts) if other or chosen not in _opts else _opts.index(chosen)))
    reply_text = f"@{sender} {_letter}：{chosen}" if sender else chosen
    try:
        _sc_qa_apply((msg or {}).get("metadata") or {}, chosen)
    except Exception:
        _log_rate_limited("quota ask apply failed")
    try:
        store.add(username, reply_text, reply_to=msg_id, channel=channel)
    except Exception:
        import traceback; traceback.print_exc()
    # Broadcast updated decision card so the UI swaps buttons to resolved state
    updated = store.get_by_id(msg_id)
    if updated:
        await _broadcast(json.dumps({"type": "message_update", "message": updated}))
    return {"ok": True, "chosen": chosen}


@app.post("/api/messages/{msg_id}/resolve_rule_proposal")
async def resolve_rule_proposal(msg_id: int, request: Request):
    """Activate or dismiss a rule proposal."""
    msg = store.get_by_id(msg_id)
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    if msg.get("type") != "rule_proposal":
        return JSONResponse({"error": "not a rule proposal"}, status_code=400)
    body = await request.json()
    action = body.get("action", "")
    meta = dict(msg.get("metadata") or {})
    rule_id = meta.get("rule_id")

    if action == "activate" and rule_id is not None:
        if not rules.activate(int(rule_id)):
            return JSONResponse({"error": "Rule no longer exists."}, status_code=409)
        meta["status"] = "activated"
    elif action == "draft" and rule_id is not None:
        if not rules.make_draft(int(rule_id)):
            return JSONResponse({"error": "Rule no longer exists."}, status_code=409)
        meta["status"] = "drafted"
    elif action == "dismiss" and rule_id is not None:
        rules.delete(int(rule_id))
        meta["status"] = "dismissed"
    else:
        return JSONResponse({"error": "invalid action"}, status_code=400)

    updated = store.update_message(msg_id, {"metadata": meta})
    if updated:
        # Broadcast the updated message so all clients re-render the card
        payload = json.dumps({"type": "edit", "message": updated})
        dead = set()
        for client in list(ws_clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.add(client)
        ws_clients.difference_update(dead)
    return updated or {"ok": True}


@app.post("/api/messages/{msg_id}/demote_rule_proposal")
async def demote_rule_proposal(msg_id: int):
    """Demote a rule_proposal message back to a regular chat message and delete the rule."""
    msg = store.get_by_id(msg_id)
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    if msg.get("type") != "rule_proposal":
        return JSONResponse({"error": "not a rule proposal"}, status_code=400)
    meta = msg.get("metadata", {})
    rule_id = meta.get("rule_id")
    if rule_id is not None:
        rules.delete(int(rule_id))
    text = meta.get("text", msg.get("text", ""))
    updated = store.update_message(msg_id, {
        "type": "chat",
        "text": text,
        "metadata": {},
    })
    if updated:
        payload = json.dumps({"type": "edit", "message": updated})
        dead = set()
        for client in list(ws_clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.add(client)
        ws_clients.difference_update(dead)
    return updated or {"ok": True}


@app.post("/api/trigger-agent")
async def trigger_agent_silent(request: Request):
    """Silently trigger an agent with a message (no chat message posted)."""
    body = await request.json()
    agent_name = body.get("agent", "").strip()
    message = body.get("message", "").strip()
    channel = body.get("channel", "general")
    source_msg_id = body.get("source_msg_id")
    if not agent_name or not message:
        return JSONResponse({"error": "agent and message required"}, status_code=400)

    custom_prompt = body.get("prompt", "").strip()
    if not custom_prompt:
        if source_msg_id is not None:
            custom_prompt = (
                f"use mcp to read #{channel} - you're mentioned, take appropriate action and respond "
                f"- conversion request: use chat history to find message #{source_msg_id} "
                f"and use chat_propose_job to propose it as a job with title<=80 chars and body<=500 chars."
            )
        else:
            custom_prompt = (
                f"use mcp to read #{channel} - you're mentioned, take appropriate action and respond "
                f"- conversion request: use chat_propose_job to propose a job from the referenced message."
            )
    # Resolve to instances if multi-instance
    targets = [agent_name]
    if registry:
        resolved = registry.resolve_to_instances(agent_name)
        if resolved:
            targets = resolved
    for target in targets:
        if agents.is_available(target):
            await agents.trigger(target, message=message, channel=channel, prompt=custom_prompt)
    return {"ok": True, "triggered": targets}


@app.post("/api/jobs")
async def create_job(request: Request):
    """Create a new job."""
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "title required"}, status_code=400)
    job_type = body.get("type", "job")
    channel = body.get("channel", "general")
    created_by = body.get("created_by", "user")
    anchor_msg_id = body.get("anchor_msg_id")
    assignee = body.get("assignee", "")
    job_body = body.get("body", "")
    result = jobs.create(
        title=title, job_type=job_type, channel=channel,
        created_by=created_by, anchor_msg_id=anchor_msg_id,
        assignee=assignee, body=job_body,
    )
    # Mark the proposal message as accepted so it persists across refresh
    if anchor_msg_id:
        anchor_msg = store.get_by_id(anchor_msg_id)
        if anchor_msg and anchor_msg.get("type") == "job_proposal":
            meta = dict(anchor_msg.get("metadata", {}))
            meta["status"] = "accepted"
            updated_msg = store.update_message(anchor_msg_id, {"metadata": meta})
            if updated_msg:
                payload = json.dumps({"type": "edit", "message": updated_msg})
                dead = set()
                for client in list(ws_clients):
                    try:
                        await client.send_text(payload)
                    except Exception:
                        dead.add(client)
                ws_clients.difference_update(dead)
    # Post breadcrumb in main timeline with job_id for clickable link
    store.add(created_by, f"Job created: {title}", msg_type="job_created",
              channel=channel, metadata={"job_id": result["id"]})
    return result


@app.patch("/api/jobs/{job_id}")
async def update_job(job_id: int, request: Request):
    """Update a job's status, title, or assignee."""
    body = await request.json()
    result = None
    if "status" in body:
        result = jobs.update_status(job_id, body["status"])
    if "title" in body:
        result = jobs.update_title(job_id, body["title"])
    if "assignee" in body:
        result = jobs.update_assignee(job_id, body["assignee"])
    if result is None:
        return JSONResponse({"error": "not found or invalid"}, status_code=404)
    return result


@app.post("/api/jobs/reorder")
async def reorder_jobs(request: Request):
    """Reorder jobs within a status group (globally, not per-channel)."""
    body = await request.json()
    status = body.get("status", "open")
    ordered_ids = body.get("ordered_ids", [])
    if not isinstance(ordered_ids, list) or len(ordered_ids) == 0:
        return JSONResponse({"error": "ordered_ids required"}, status_code=400)
    updated = jobs.reorder(status=status, ordered_ids=ordered_ids)
    return {"ok": True, "updated": len(updated)}


@app.get("/api/jobs/{job_id}/messages")
async def get_job_messages(job_id: int):
    """Get all messages in a job."""
    msgs = jobs.get_messages(job_id)
    if msgs is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return msgs


@app.post("/api/jobs/{job_id}/messages")
async def post_job_message(job_id: int, request: Request):
    """Post a message to a job."""
    body = await request.json()
    text = body.get("text", "").strip()
    sender = body.get("sender", "user")
    attachments = body.get("attachments", [])
    if not text and not attachments:
        return JSONResponse({"error": "text or attachments required"}, status_code=400)
    msg_type = body.get("type", "chat")
    msg = jobs.add_message(job_id, sender, text,
                           attachments=attachments, msg_type=msg_type)
    if msg is None:
        return JSONResponse({"error": "job not found"}, status_code=404)

    # Route @mentions in job messages to agents (with job_id context)
    job = jobs.get(job_id)
    if job:
        channel = job.get("channel", "general")
        raw_targets = router.get_targets(sender, text, channel)
        targets = []
        for t in raw_targets:
            if registry:
                targets.extend(registry.resolve_to_instances(t))
            else:
                targets.append(t)
        targets = list(dict.fromkeys(targets))

        import mcp_bridge
        chat_msg = f"{sender}: {text}" if text else ""
        for target in targets:
            if registry:
                inst = registry.get_instance(target)
                if inst and inst.get("state") == "pending":
                    continue
            if agents.is_available(target):
                await agents.trigger(target, message=chat_msg, channel=channel,
                                     job_id=job_id)

    return msg


@app.delete("/api/jobs/{job_id}/messages/{msg_id}")
async def delete_job_message(job_id: int, msg_id: int):
    """Soft-delete a message in a job thread."""
    result = jobs.delete_message(job_id, msg_id)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True, **result}


@app.post("/api/jobs/{job_id}/messages/{msg_index}/resolve")
async def resolve_job_message(job_id: int, msg_index: int, request: Request):
    """Resolve a suggestion message (accept/dismiss)."""
    body = await request.json()
    resolution = body.get("resolution", "dismissed")
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    msgs = job.get("messages", [])
    if msg_index < 0 or msg_index >= len(msgs):
        return JSONResponse({"error": "invalid message index"}, status_code=400)
    msg = msgs[msg_index]
    msg["resolved"] = resolution
    jobs._save()

    # If accepted, trigger the suggesting agent with context
    if resolution == "accepted" and msg.get("sender"):
        agent_name = msg["sender"]
        channel = job.get("channel", "general")
        if agents.is_available(agent_name):
            await agents.trigger(agent_name,
                                 message=f"Your suggestion was accepted: {msg.get('text', '')}",
                                 channel=channel, job_id=job_id)

    return {"ok": True, "resolution": resolution}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int, request: Request):
    """Delete or archive a job. ?permanent=true for real delete."""
    permanent = request.query_params.get("permanent", "").lower() == "true"
    if permanent:
        result = jobs.delete(job_id)
    else:
        result = jobs.update_status(job_id, "archived")
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return result


_AVATAR_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}  # no .svg: it can carry script


def _scranton_team() -> dict:
    """Per-teammate display info from config.toml (Scranton).

    avatar: a file name inside static/avatars/ (e.g. "pm-bear.jpg"); anything
    with a path separator or an unknown extension is ignored.
    """
    out = {}
    avatar_dir = Path(__file__).parent / "static" / "avatars"
    for name, cfg in (config or {}).get("agents", {}).items():
        if not isinstance(cfg, dict):
            continue
        command = str(cfg.get("command", "") or "")
        provider = Path(command).name if command else ""
        if provider in ("agent", "cursor-agent"):
            provider = "cursor"
        elif provider == "agy":
            provider = "gemini"
        avatar = str(cfg.get("avatar", "") or "").strip()
        url = ""
        if avatar and "/" not in avatar and "\\" not in avatar and Path(avatar).suffix.lower() in _AVATAR_EXTS:
            if (avatar_dir / avatar).is_file():
                url = f"/static/avatars/{avatar}"
        out[name] = {
            "label": str(cfg.get("label", name)),
            "role": str(cfg.get("role", "") or ""),
            "provider": provider,
            "avatar": url,
            "autostart": bool(cfg.get("autostart", True)),
            # what the @ list shows on the right: model and effort, not the handle
            "model_name": _sc_team.model_label(_sc_team.provider_of(command), str(cfg.get("model", "") or "")),
            "effort": str(cfg.get("effort", "") or ""),
            "mentions_owner": name.lower() == _mentions_from(),
        }
    return out


import scranton_ops as _scranton_ops  # noqa: E402  (update check + resume stopped teammates)
import scranton_team as _sc_team  # noqa: E402  (connections, model, profile)
_scranton_ops.install(app, lambda: config)


@app.get("/api/scranton/team")
async def scranton_team():
    return JSONResponse(_scranton_team())


_ME_AVATAR = Path(__file__).parent / "data" / "me-avatar.txt"   # data/ is gitignored: never pushed


@app.get("/api/scranton/me/avatar")
async def scranton_me_avatar():
    try:
        return JSONResponse({"data": _ME_AVATAR.read_text("utf-8").strip()})
    except OSError:
        return JSONResponse({"data": ""})


@app.post("/api/scranton/me/avatar")
async def scranton_me_avatar_set(request: Request):
    body = await request.json()
    data = str(body.get("data", "") or "").strip()
    if data and (not _re.match(r"^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$", data) or len(data) > 400_000):
        return JSONResponse({"error": "use a JPG, PNG or WebP picture"}, status_code=400)
    _ME_AVATAR.parent.mkdir(parents=True, exist_ok=True)
    if data:
        atomic_write(_ME_AVATAR, data, "utf-8")
    else:
        _ME_AVATAR.unlink(missing_ok=True)
    await broadcast_team_changed()
    return JSONResponse({"ok": True})


@app.post("/api/scranton/avatars")
async def scranton_avatar_upload(request: Request):
    """A new teammate picture from Settings (the page crops it to a 256 px square JPEG first).
    Saved as static/avatars/upload-<handle>-<time>.jpg, which git ignores (never pushed)."""
    import base64 as _b64
    body = await request.json()
    handle = str(body.get("handle", "") or "").strip().lower()
    data = str(body.get("data", "") or "")
    m = _re.match(r"^data:image/jpeg;base64,([A-Za-z0-9+/=]+)$", data)
    if not m or len(data) > 400_000:
        return JSONResponse({"error": "use a JPG, PNG or WebP picture"}, status_code=400)
    raw = _b64.b64decode(m.group(1))
    if not raw.startswith(b"\xff\xd8\xff"):          # really a JPEG
        return JSONResponse({"error": "use a JPG, PNG or WebP picture"}, status_code=400)
    safe = _re.sub(r"[^a-z0-9-]", "", handle)[:20] or "agent"   # also for a teammate being added (no handle yet)
    fname = f"upload-{safe}-{int(_time_pr.time())}.jpg"
    (Path(__file__).parent / "static" / "avatars" / fname).write_bytes(raw)
    return JSONResponse({"ok": True, "file": fname})   # the page then sets it like any other picture


@app.post("/api/scranton/avatars/fetch")
async def scranton_avatar_fetch(request: Request):
    """A picture link pasted in Settings: fetch it here (the page can't, other sites block it),
    hand the image back as a data URL; the page crops and uploads it like a local file.
    http(s) only, images only, at most 5 MB, not this machine or the local network."""
    import base64 as _b64
    import ipaddress as _ip
    import socket as _sock
    import urllib.parse as _up
    import urllib.request as _ur
    url = str((await request.json()).get("url", "") or "").strip()
    u = _up.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return JSONResponse({"error": "paste a link that starts with https://"}, status_code=400)
    _cgnat = _ip.ip_network("100.64.0.0/10")   # Tailscale and carrier NAT: your own devices

    def _bad_host(host):
        try:
            for info in _sock.getaddrinfo(host, None):
                a = _ip.ip_address(info[4][0].split("%")[0])
                if (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast
                        or a.is_unspecified or (a.version == 4 and a in _cgnat)):
                    return "that link points to this computer or the local network"
        except Exception:
            return "couldn't find that site"
        return None

    class _NoRedirect(_ur.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None   # we follow redirects ourselves, checking each new address

    opener = _ur.build_opener(_NoRedirect)

    def _get():
        cur = url
        for _ in range(4):
            cu = _up.urlparse(cur)
            if cu.scheme not in ("http", "https") or not cu.hostname:
                return None, "couldn't download that picture"
            bad = _bad_host(cu.hostname)
            if bad:
                return None, bad
            req = _ur.Request(cur, headers={"User-Agent": "Scranton (local team chat)", "Accept": "image/*"})
            try:
                r = opener.open(req, timeout=10)
            except _ur.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                    cur = _up.urljoin(cur, e.headers["Location"])
                    continue
                return None, "couldn't download that picture"
            except Exception:
                return None, "couldn't download that picture"
            with r:
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ctype not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                    return None, "that link isn't a picture"
                data = r.read(5 * 1024 * 1024 + 1)
                if len(data) > 5 * 1024 * 1024:
                    return None, "that picture is bigger than 5 MB"
                return f"data:{ctype};base64," + _b64.b64encode(data).decode(), None
        return None, "that link redirects too many times"
    data, err = await asyncio.to_thread(_get)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return JSONResponse({"data": data})


import scranton_avatar_gen as _sc_avgen  # noqa: E402


@app.post("/api/scranton/avatars/generate")
async def scranton_avatar_generate(request: Request):
    """Draw a new picture in the team's style with ChatGPT (Codex, subscription). Background job."""
    b = await request.json()
    r = _sc_avgen.start(str(b.get("label", "") or "")[:40], str(b.get("role", "") or "")[:300],
                        str(b.get("handle", "") or ""), str(b.get("like", "") or ""))
    return JSONResponse(r, status_code=400 if r.get("error") else 200)


@app.get("/api/scranton/avatars/generate/{jid}")
async def scranton_avatar_generate_status(jid: str):
    return JSONResponse(_sc_avgen.status(jid))


@app.get("/api/scranton/connections")
async def scranton_connections():
    return JSONResponse(await asyncio.to_thread(_sc_team.connections, config))


@app.post("/api/scranton/connections/{provider}/login")
async def scranton_connection_login(provider: str):
    return JSONResponse(await asyncio.to_thread(_sc_team.open_login, provider))


@app.get("/api/scranton/daily")
async def scranton_daily_get():
    ids = _daily_ids(config)
    on = [x for x in (schedules.get(i) for i in ids) if x]
    return JSONResponse({"enabled": bool(on) and all(x.get("active", True) for x in on),
                         "times": [x.get("daily_at") for x in on]})


@app.post("/api/scranton/daily")
async def scranton_daily_set(request: Request):
    """Daily plan (morning) and summary (evening) from the PM: on or off."""
    on = bool((await request.json()).get("enabled"))
    for i in _daily_ids(config):
        schedules.set_fields(i, active=on)
    return JSONResponse({"ok": True, "enabled": on})


@app.get("/api/scranton/channel/{name}/about")
async def scranton_channel_about(name: str):
    """Slack-style channel details: topic, description, when it started, its files."""
    name = name.strip().lower()
    if name not in room_settings.get("channels", []):
        return JSONResponse({"error": "no such channel"}, status_code=404)
    meta = (room_settings.get("channel_meta") or {}).get(name) or {}
    first = None
    files = []
    for m in store.get_since(-1):
        if (m.get("channel") or "general") != name:
            continue
        if first is None:
            first = m.get("timestamp")
        for a in m.get("attachments") or []:
            if isinstance(a, dict) and str(a.get("url", "")).startswith("/uploads/"):
                files.append({"name": str(a.get("name") or "file")[:200], "url": a["url"], "size": a.get("size"),
                              "by": m.get("sender"), "time": m.get("timestamp"), "msg": m.get("id")})
    return JSONResponse({"name": name, "topic": meta.get("topic", ""), "description": meta.get("description", ""),
                         "started": first, "files": files[-20:][::-1]})


@app.post("/api/scranton/channel/{name}/about")
async def scranton_channel_about_set(name: str, request: Request):
    name = name.strip().lower()
    if name not in room_settings.get("channels", []):
        return JSONResponse({"error": "no such channel"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "expected {topic, description}"}, status_code=400)
    meta = room_settings.setdefault("channel_meta", {}).setdefault(name, {})
    for key, limit in (("topic", 250), ("description", 1000)):
        if key in body:
            meta[key] = " ".join(str(body.get(key) or "").split())[:limit] if key == "topic" else str(body.get(key) or "").strip()[:limit]
    _save_settings()
    return JSONResponse({"ok": True, "topic": meta.get("topic", ""), "description": meta.get("description", "")})


@app.get("/api/scranton/team-permissions")
async def scranton_team_permissions():
    return JSONResponse(_sc_team.team_permissions(str((config or {}).get("team", {}).get("permissions", "ask"))))


@app.post("/api/scranton/team-permissions")
async def scranton_team_permissions_set(request: Request):
    try:
        body = await request.json()
        return JSONResponse(_sc_team.set_team_permissions(str((body or {}).get("permissions", ""))))
    except (ValueError, AttributeError) as e:
        return JSONResponse({"error": str(e) or "permissions is full or ask"}, status_code=400)


@app.get("/api/scranton/channel-stats")
async def scranton_channel_stats(channel: str):
    """What deleting a channel would take away: its messages, files and members (Lu, 11-10)."""
    msgs = [m for m in store.get_since(-1) if (m.get("channel") or "general") == channel]
    files = sum(1 for m in msgs for a in (m.get("attachments") or []) if isinstance(a, dict))
    return JSONResponse({"messages": len(msgs), "files": files, "members": _channel_members(channel),
                         "first": msgs[0].get("timestamp") if msgs else None})


@app.get("/api/scranton/inbox-feed")
async def scranton_inbox_feed(days: int = 7):
    """What Activity needs, without loading every message: from the last `days`, your own messages
    (to know what you answered) and teammates' messages that @ you, reply to you or are DMs."""
    days = max(1, min(int(days), 30))
    since = _time_feed.time() - days * 86400
    owner = str(room_settings.get("username", "") or "").lower()
    tag = _re.compile(r"(^|[^\w])@(" + _re.escape(owner) + r"|lu)(?![\w-])", _re.I) if owner else None
    mine, out = set(), []
    for m in store.get_since(-1):
        if float(m.get("timestamp") or 0) < since:
            continue
        who = str(m.get("sender", "")).lower()
        text = str(m.get("text") or "")
        if who == owner:
            mine.add(m.get("id")); out.append(m)
        elif (str(m.get("channel", "")).startswith("dm-") or m.get("reply_to") in mine
              or (tag and tag.search(text)) or (who == "system" and text.startswith("Loop guard:"))):
            out.append(m)
    return JSONResponse({"messages": out[-3000:]})


@app.get("/api/scranton/older")
async def scranton_older(channel: str, before: int, limit: int = 100):
    """Messages in `channel` older than id `before` (the page only gets the last HISTORY_CAP
    per channel when it opens; scrolling up asks for the rest)."""
    limit = max(1, min(int(limit), 200))
    older = [m for m in store.get_since(-1)
             if (m.get("channel") or "general") == channel and int(m.get("id", 0)) < int(before)]
    return JSONResponse({"messages": older[-limit:], "more": len(older) > limit})


HANDOVER_DEFAULTS = {"enabled": False, "hours": 4, "wakes": 40, "context_k": 100}   # context_k: start over past this many thousand tokens per call (Lu, 11-10; 100 is a starting point)


def _handover_settings() -> dict:
    h = room_settings.get("handover") or {}
    out = dict(HANDOVER_DEFAULTS)
    if isinstance(h, dict):
        out.update({k: h[k] for k in HANDOVER_DEFAULTS if k in h})
    return out


@app.get("/api/scranton/handover")
async def scranton_handover():
    """Fresh-session handover: on/off and when (hours in one session, or messages handled).
    Wrappers read this before each new message."""
    return JSONResponse(_handover_settings())


@app.post("/api/scranton/handover")
async def scranton_handover_set(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "expected {enabled, hours, wakes}"}, status_code=400)
    cur = _handover_settings()
    if "enabled" in body:
        cur["enabled"] = bool(body["enabled"])
    try:
        if "hours" in body:
            cur["hours"] = max(1, min(int(body["hours"]), 48))
        if "wakes" in body:
            cur["wakes"] = max(10, min(int(body["wakes"]), 500))
        if "context_k" in body:
            cur["context_k"] = 0 if not body["context_k"] else max(30, min(int(body["context_k"]), 900))
    except (TypeError, ValueError):
        return JSONResponse({"error": "hours and wakes are numbers"}, status_code=400)
    room_settings["handover"] = cur
    _save_settings()
    return JSONResponse(cur)


@app.get("/api/scranton/dm-activity")
async def scranton_dm_activity():
    """Latest message time per direct-message channel that has real messages (not join/leave
    notices), so the sidebar lists only conversations you've actually had, like Slack."""
    last = {}
    for m in store.get_since(-1):
        ch = str(m.get("channel") or "")
        if ch.startswith("dm-") and m.get("type", "chat") == "chat" and m.get("sender") != "system":
            last[ch] = max(last.get(ch, 0), float(m.get("timestamp") or 0))
    return JSONResponse(last)


# --- PR state for Activity ----------------------------------------------------------------
# "Please merge #93" in Activity is done once #93 is merged on GitHub: Lu doesn't report back
# (Lu, 11-09). Read-only `gh pr view`, cached; on any GitHub error we back off instead of retrying.
import re as _re_pr
import shutil as _shutil_pr
import time as _time_pr
import subprocess as _sp_pr

_PR_URL = _re_pr.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)$")
_pr_cache: dict = {}          # url -> (state, checked_at)
_pr_backoff_until = [0.0]
_PR_TTL = {"MERGED": 24 * 3600, "CLOSED": 24 * 3600}   # final states rarely change; OPEN is rechecked


def _pr_state(url: str):
    now = _time_pr.time()
    hit = _pr_cache.get(url)
    if hit and now - hit[1] < (_PR_TTL.get(hit[0], 180) if hit[0] else 600):
        return hit[0]
    if now < _pr_backoff_until[0] or not _shutil_pr.which("gh"):
        return hit[0] if hit else None
    try:
        r = _sp_pr.run(["gh", "pr", "view", url, "--json", "state", "-q", ".state"],
                       capture_output=True, text=True, timeout=15)
    except Exception:
        return hit[0] if hit else None
    out = (r.stdout or "").strip().upper()
    if r.returncode != 0 or out not in ("OPEN", "MERGED", "CLOSED"):
        err = (r.stderr or "").lower()
        if any(k in err for k in ("rate limit", "403", "429", "suspended", "abuse")):
            _pr_backoff_until[0] = now + 1800   # harness rule: GitHub said stop, so stop for a while
            log.warning("PR state: GitHub refused (%s); not asking again for 30 min", err.strip()[:120])
        elif not hit:
            _pr_cache[url] = (None, now)   # no access / no such PR: don't ask GitHub again for 10 min
        return hit[0] if hit else None
    _pr_cache[url] = (out, now)
    return out


@app.get("/api/scranton/pr-state")
async def scranton_pr_state(request: Request):
    urls = [u for u in request.query_params.getlist("u") if _PR_URL.match(u)][:20]
    sem = asyncio.Semaphore(4)   # a few at a time: one bot account for every agent (harness rule)

    async def one(u):
        async with sem:
            return await asyncio.to_thread(_pr_state, u)
    try:
        got = await asyncio.wait_for(asyncio.gather(*(one(u) for u in urls)), 25)
    except asyncio.TimeoutError:
        got = [(_pr_cache.get(u) or (None,))[0] for u in urls]
    return JSONResponse(dict(zip(urls, got)))


@app.get("/api/scranton/report")
async def scranton_report(days: int = 7):
    days = max(1, min(int(days), 31))
    owner = str(room_settings.get("username") or config.get("team", {}).get("owner", "Lu"))
    team = {n: a for n, a in config.get("agents", {}).items()}
    msgs = store.get_since(-1)
    # Same answer for a minute unless a message or the estimate changed: the page re-asks often.
    key = (days, owner, len(msgs), msgs[-1]["id"] if msgs else -1, _sc_report.settings().get("minutes_per_pr"))
    hit = _report_cache.get("v")
    import time as _t
    if hit and hit[0] == key and _t.time() - hit[1] < 60:
        return JSONResponse(hit[2])
    data = await asyncio.to_thread(_sc_report.build, msgs, team, owner, days)
    _report_cache["v"] = (key, _t.time(), data)
    return JSONResponse(data)


_report_cache: dict = {}


import scranton_tokens as _sc_tokens  # noqa: E402


_tok_last: dict = {}
_tok_jobs: dict = {}


# Report → "What changed": per-day numbers and the changes Lu picked (kept on the server, so the
# Mac app and the phone show the same ones; they used to live in one browser's localStorage).
# Changes made on Lu's say-so outside the Report's own cards, shown with the same before/after.
_SEEDED_CHANGES = [
    {"id": "at-only-who-acts", "title": "@ only whoever must act now", "key": "A", "at": 1794311400000, "by": "Claude, you agreed"},
    {"id": "reports-no-at", "title": "Reports and 收到 without @", "key": "A", "at": 1794311520000, "by": "Claude, you agreed"},
    {"id": "fresh-by-size", "title": "Fresh session past 100k re-read", "key": "A", "at": 1794312300000, "by": "Claude, you agreed"},
]


def _report_changes() -> list:
    cur = [c for c in room_settings.get("report_changes", []) if isinstance(c, dict)]
    seeded = set(room_settings.get("report_changes_seeded", []))
    new = [c for c in _SEEDED_CHANGES if c["id"] not in seeded]
    if new:
        have = {c.get("id") for c in cur}
        cur += [dict(c) for c in new if c["id"] not in have]
        room_settings["report_changes"] = sorted(cur, key=lambda c: c.get("at", 0))[-40:]
        room_settings["report_changes_seeded"] = sorted(seeded | {c["id"] for c in new})
        _save_settings()
    return room_settings.get("report_changes", [])


@app.get("/api/scranton/report/changes")
async def scranton_report_changes_get():
    return JSONResponse({"changes": _report_changes()})


@app.get("/api/scranton/report/trend")
async def scranton_report_trend(days: int = 14):
    days = max(3, min(int(days), 31))
    team = {n: a for n, a in config.get("agents", {}).items()}
    series = await asyncio.to_thread(_sc_tokens.daily, store.get_since(-1), team, days)
    return JSONResponse({"days": series, "changes": _report_changes()})


@app.post("/api/scranton/report/changes")
async def scranton_report_changes(request: Request):
    """Record a change Lu picked: {id, title, key, at (ms)}. Same id again replaces it."""
    try:
        body = await request.json()
    except Exception:
        body = None
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return JSONResponse({"error": "expected {items: [...]}"}, status_code=400)
    cur = {c.get("id"): c for c in _report_changes() if isinstance(c, dict)}
    for it in items[:20]:
        if not isinstance(it, dict) or not str(it.get("id") or "").strip():
            continue
        try:
            at = int(it.get("at") or 0)
        except (TypeError, ValueError):
            continue
        cid = str(it["id"])[:60]
        if cid in cur and it.get("merge_only"):
            continue   # a browser's old local pick doesn't overwrite what the server has
        cur[cid] = {"id": cid, "title": str(it.get("title") or cid)[:120], "key": str(it.get("key") or "")[:2],
                    "at": at, "by": str(it.get("by") or "Lu")[:20]}
    room_settings["report_changes"] = sorted(cur.values(), key=lambda c: c["at"])[-40:]
    _save_settings()
    return JSONResponse({"changes": room_settings["report_changes"]})


@app.get("/api/scranton/report/tokens")
async def scranton_report_tokens(days: int = 7, shape: int = 0):
    """Tokens from Claude Code / Codex session logs on this Mac, per teammate and per task."""
    if shape:   # diagnostics: kinds of Codex log lines that carry a sender (no content)
        return JSONResponse(await asyncio.to_thread(_sc_tokens.codex_shape))
    days = max(1, min(int(days), 31))
    last = _tok_last.get(days)
    if last and _time_pr.time() - last[0] < 120:
        return JSONResponse(last[1])
    task = _tok_jobs.get(days)
    if task is None or task.done():
        owner = str(room_settings.get("username") or config.get("team", {}).get("owner", "Lu"))
        team = {n: a for n, a in config.get("agents", {}).items()}

        async def run():
            t0 = _time_pr.time()
            data = await asyncio.to_thread(_sc_tokens.build, store.get_since(-1), team, owner, days)
            data = {**data, "took_s": round(_time_pr.time() - t0, 1)}
            _tok_last[days] = (_time_pr.time(), data)
            return data
        task = _tok_jobs[days] = asyncio.create_task(run())
    try:
        # first read of big logs can take a while: don't hold the request (or the page) on it
        return JSONResponse(await asyncio.wait_for(asyncio.shield(task), 6))
    except asyncio.TimeoutError:
        if last:
            return JSONResponse({**last[1], "stale": True})
        return JSONResponse({"pending": True})
    except Exception as e:  # noqa: BLE001
        log.warning("token report failed: %s", e)
        return JSONResponse({"available": False, "error": str(e)[:200]})


@app.post("/api/scranton/report/settings")
async def scranton_report_settings(request: Request):
    b = await request.json()
    try:
        return JSONResponse(_sc_report.set_minutes_per_pr(b.get("minutes_per_pr")))
    except (ValueError, TypeError) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


def _pm_channel() -> str:
    """Where the project manager plans the day: the daily-plan schedule's channel."""
    for item in (config or {}).get("team", {}).get("schedules", []) or []:
        if item.get("id") == "daily-plan" and item.get("channel"):
            return str(item["channel"])
    return "general"


@app.post("/api/scranton/presence")
async def scranton_presence(request: Request):
    """The page pings this while Lu is looking. Back after 2+ hours: ask the PM for one list."""
    away = _sc_presence.seen()
    if away and "pm" in ((config or {}).get("agents") or {}):
        owner = room_settings.get("username") or "Lu"
        store.add("Scranton", _sc_presence.catch_up_text(owner, away), channel=_pm_channel())
        return JSONResponse({"ok": True, "caught_up": True})
    return JSONResponse({"ok": True})


def _grok_labels() -> dict:
    labels = {n: str(a.get("label") or n) for n, a in ((config or {}).get("agents") or {}).items()}
    labels[_sc_grok.HANDLE] = _sc_grok.LABEL
    return labels


@app.post("/api/scranton/grok/say")
async def scranton_grok_say(request: Request):
    """Grok Bot posts as 幕僚长 (Grok). Only into an existing channel or an agent's DM."""
    b = await request.json()
    channel = str(b.get("channel") or "").strip().lstrip("#").lower()
    text = str(b.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "nothing to send"}, status_code=400)
    if len(text) > _sc_grok.MAX_TEXT:
        return JSONResponse({"ok": False, "error": f"too long (max {_sc_grok.MAX_TEXT} characters)"}, status_code=400)
    if channel not in room_settings.get("channels", []):
        return JSONResponse({"ok": False, "error": f"no channel #{channel}. Channels: " + ", ".join(
            c for c in room_settings.get("channels", []) if not c.startswith("dm-"))}, status_code=400)
    reply_to = b.get("reply_to")
    try:
        reply_to = int(reply_to) if reply_to not in (None, "") else None
    except (TypeError, ValueError):
        reply_to = None
    if reply_to is not None and not store.get_by_id(reply_to):
        reply_to = None
    if _re.match(r"^(?:@\S+\s+)*/", text):
        # /continue, /clear, /roastreview… are yours: Grok relays words, it doesn't run commands.
        return JSONResponse({"ok": False, "error": "Grok can't send commands (text starting with /). Ask Lu."}, status_code=400)
    text = _grok_handles(text)
    # Grok talks to the project manager only (Lu, 2026-11-08): two people giving the team
    # orders would clash. @Lu is fine; any other teammate is refused.
    lead = _grok_lead()
    others = sorted({m.lower() for m in _re.findall(r"@([\w-]+)", text)}
                    & {h.lower() for h in ((config or {}).get("agents") or {})} - {lead})
    if others:
        return JSONResponse({"ok": False, "error": f"Grok only @s the project manager (@{_grok_labels().get(lead, lead)}). "
                             f"Not: {', '.join('@' + o for o in others)}. Ask the project manager to pass it on."}, status_code=400)
    msg = store.add(_sc_grok.HANDLE, text, channel=channel, reply_to=reply_to)
    return JSONResponse({"ok": True, "id": msg["id"]})


def _grok_lead() -> str:
    """The one teammate Grok may @: the project manager (handle pm, else the first agent whose label says so)."""
    agents = (config or {}).get("agents") or {}
    if "pm" in agents:
        return "pm"
    for h, a in agents.items():
        if "项目经理" in str(a.get("label") or "") or "project manager" in str(a.get("label") or "").lower():
            return h
    return "pm"


def _grok_handles(text: str) -> str:
    """Grok writes @项目经理 like Lu does; turn labels into handles so they reach the agent."""
    for h, a in ((config or {}).get("agents") or {}).items():
        lab = str(a.get("label") or "")
        if lab and f"@{lab}" in text:
            text = text.replace(f"@{lab}", f"@{h}")
    return text


@app.get("/api/scranton/grok/read")
async def scranton_grok_read(channel: str = "", since: int = -1, limit: int = 30, mentions: bool = False):
    """Recent messages as plain lines. mentions=1: what @s grok or the owner, in any channel."""
    limit = max(1, min(int(limit), 200))
    owner = str(room_settings.get("username") or "Lu")
    msgs = [m for m in store.get_since(int(since)) if m.get("type", "chat") == "chat"]
    if channel:
        ch = channel.strip().lstrip("#").lower()
        msgs = [m for m in msgs if m.get("channel", "general") == ch]
    if mentions:
        tag = _re.compile(r"@(" + _re.escape(_sc_grok.HANDLE) + "|" + _re.escape(owner) + r")(?![\w-])", _re.I)
        msgs = [m for m in msgs if tag.search(str(m.get("text") or ""))]
    labels = _grok_labels()
    labels[owner.lower()] = owner
    lines = [_sc_grok.line(m, labels) for m in msgs[-limit:]]
    return JSONResponse({"ok": True, "last_id": msgs[-1]["id"] if msgs else int(since), "lines": lines})


@app.get("/api/scranton/grok/status")
async def scranton_grok_status():
    """Channels and who's working, so Grok knows where to post."""
    agents_cfg = (config or {}).get("agents") or {}
    import mcp_bridge
    def _state(h):
        if any(mcp_bridge._activity.get(n) for n in list(mcp_bridge._activity) if n.split("-")[0] == h):
            return "working"
        return "online" if agents and agents.is_available(h) else "not running"
    team = {h: {"label": a.get("label", h), "state": _state(h), "doing": _sc_doing.get(h, "")} for h, a in agents_cfg.items()}
    return JSONResponse({"ok": True, "owner": room_settings.get("username"),
                         "channels": [c for c in room_settings.get("channels", []) if not c.startswith("dm-")], "team": team})


@app.get("/api/scranton/shortcuts")
async def scranton_shortcuts_get():
    return JSONResponse(_sc_shortcuts.load())


@app.post("/api/scranton/shortcuts")
async def scranton_shortcuts_set(request: Request):
    try:
        return JSONResponse(_sc_shortcuts.save((await request.json()).get("items")))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.get("/api/scranton/catchup")
async def scranton_catchup_get():
    return JSONResponse(_sc_presence.settings())


@app.post("/api/scranton/catchup")
async def scranton_catchup_set(request: Request):
    b = await request.json()
    return JSONResponse(_sc_presence.set_enabled(bool(b.get("enabled", True))))


@app.get("/api/scranton/backup")
async def scranton_backup_get():
    return JSONResponse(_sc_backup.settings())


@app.post("/api/scranton/backup")
async def scranton_backup_set(request: Request):
    b = await request.json()
    try:
        return JSONResponse(_sc_backup.set_settings(
            enabled=b.get("enabled") if "enabled" in b else None,
            folder=b.get("folder") if "folder" in b else None))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/api/scranton/backup/now")
async def scranton_backup_now():
    return JSONResponse(await asyncio.to_thread(_sc_backup.backup_now))


@app.get("/api/scranton/backup/export")
async def scranton_backup_export():
    from fastapi.responses import Response
    raw = await asyncio.to_thread(_sc_backup.export_bytes)
    name = _sc_backup.file_name()
    return Response(raw, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/scranton/backup/import")
async def scranton_backup_import(file: UploadFile = File(...)):
    raw = await file.read(512 * 1024 * 1024 + 1)
    if len(raw) > 512 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "This file is larger than 512 MB."}, status_code=400)
    try:
        result = await asyncio.to_thread(_sc_backup.stage_import, raw)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    _scranton_ops._restart_server_soon()
    return JSONResponse(result)


@app.get("/api/scranton/quiet")
async def scranton_quiet_get():
    return JSONResponse(_sc_team.quiet_hours())


@app.post("/api/scranton/quiet")
async def scranton_quiet_set(request: Request):
    b = await request.json()
    try:
        return JSONResponse(_sc_team.set_quiet_hours(b.get("enabled", True), str(b.get("from", "")), str(b.get("to", ""))))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.get("/api/scranton/models/new")
async def scranton_models_new():
    """New models an app offers since you last looked (for the 'new model' card)."""
    return JSONResponse(await asyncio.to_thread(_sc_team.new_models))


@app.post("/api/scranton/models/{provider}/seen")
async def scranton_models_seen(provider: str):
    try:
        await asyncio.to_thread(_sc_team.mark_models_seen, provider)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True})


@app.post("/api/scranton/connections/{provider}/default")
async def scranton_connection_default(provider: str, request: Request):
    """Default model for this app's agents (applies the next time each one starts)."""
    body = await request.json()
    try:
        r = _sc_team.set_provider_default(provider, str(body.get("model", "")))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    await broadcast_team_changed()
    return JSONResponse(r)


@app.get("/api/scranton/teammate/{name}")
async def scranton_teammate(name: str):
    recent = []
    for m in reversed(store.get_since(-1)):
        if str(m.get("sender", "")).lower() == name or str(m.get("sender", "")).lower().startswith(name + "-"):
            recent.append({k: m.get(k) for k in ("id", "text", "channel", "time", "timestamp")})
            if len(recent) >= 20:
                break
    p = _sc_team.profile(name, config, room_settings.get("channel_members") or {}, recent)
    if not p:
        return JSONResponse({"error": "not found"}, status_code=404)
    p["running"] = agents.is_available(name)
    p["on_api"] = _sc_keys.on_api(name)
    p["has_backup_key"] = bool(_sc_keys.get_key(_sc_keys.provider_of_command(((config or {}).get("agents", {}).get(name) or {}).get("command", ""))))
    return JSONResponse(p)


def _sc_tmux_session(name: str) -> str:
    """The terminal of the instance that's actually running: 'help', or 'help-2' when the
    registry gave it a numbered slot. Falls back to the plain name."""
    try:
        live = [n for n, d in registry.get_all().items()
                if d.get("base") == name and d.get("state", "active") == "active"]
    except Exception:
        live = []
    # A wrapper's terminal keeps the name it started with, even if the registry later renamed
    # it (claude -> claude-1), so use the first candidate whose terminal really exists.
    import subprocess as _sp
    for cand in ([name] if name in live else []) + sorted(live) + [name]:
        try:
            if _sp.run(["tmux", "has-session", "-t", f"=agentchattr-{cand}"], capture_output=True, timeout=3).returncode == 0:
                return f"agentchattr-{cand}"
        except Exception:
            break
    try:
        out = _sp.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, timeout=3).stdout.split()
        found = sorted(s for s in out if _re.fullmatch(rf"agentchattr-{_re.escape(name)}(-\d+)?", s))
        if found:
            return found[0]
    except Exception:
        pass
    return f"agentchattr-{name}"


@app.get("/api/scranton/teammate/{name}/screen")
async def scranton_teammate_screen(name: str):
    """What the agent's terminal shows right now (read-only), so Lu can see a stuck prompt."""
    if name not in (config or {}).get("agents", {}):
        return JSONResponse({"error": "not found"}, status_code=404)
    import subprocess as _sp
    def grab():
        r = _sp.run(["tmux", "capture-pane", "-p", "-J", "-t", f"={_sc_tmux_session(name)}:", "-S", "-60"],
                    capture_output=True, text=True, timeout=5)
        return r.returncode, r.stdout
    try:
        code, out = await asyncio.to_thread(grab)
    except Exception:
        code, out = 1, ""
    if code != 0:
        return JSONResponse({"running": False, "text": ""})
    text = _re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", out).rstrip()
    return JSONResponse({"running": True, "text": "\n".join(text.splitlines()[-60:])})


@app.post("/api/scranton/teammate/{name}/keys")
async def scranton_teammate_keys(name: str, request: Request):
    """Answer a prompt on the agent's screen: Enter, Esc, arrows, 1-9, y/n. Nothing else can be typed."""
    if name not in (config or {}).get("agents", {}):
        return JSONResponse({"error": "not found"}, status_code=404)
    key = str((await request.json()).get("key", ""))
    allowed = {"Enter": "Enter", "Escape": "Escape", "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right", "Tab": "Tab",
               **{str(i): str(i) for i in range(1, 10)}, "y": "y", "n": "n"}
    if key not in allowed:
        return JSONResponse({"error": "not allowed"}, status_code=400)
    import subprocess as _sp
    target = f"={_sc_tmux_session(name)}:"
    # Raw bytes, not tmux key names: an app that turned on extended keys (Antigravity's agy) gets
    # tmux's "Enter" as an escape sequence and ignores it (Lu, 11-10: Enter did nothing).
    raw = {"Enter": "0d", "Escape": "1b", "Tab": "09", "Up": "1b 5b 41", "Down": "1b 5b 42",
           "Right": "1b 5b 43", "Left": "1b 5b 44"}
    cmd = ["tmux", "send-keys", "-t", target] + (["-H", *raw[key].split()] if key in raw else ["-l", allowed[key]])
    r = await asyncio.to_thread(_sp.run, cmd, capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return JSONResponse({"error": (r.stderr or "couldn't reach the terminal").strip()[:200]}, status_code=502)
    return JSONResponse({"ok": True})


@app.post("/api/scranton/teammate/{name}/open-terminal")
async def scranton_teammate_open_terminal(name: str):
    """Open the agent's real terminal in macOS Terminal (Lu, 11-10: "做成真的可以用的"). Only on the Mac
    Scranton runs on; the command is fixed (tmux attach to that agent), nothing from the request is run."""
    if name not in (config or {}).get("agents", {}):
        return JSONResponse({"error": "not found"}, status_code=404)
    import shutil as _sh
    import subprocess as _sp
    if sys.platform != "darwin" or not _sh.which("osascript"):
        return JSONResponse({"error": "Opening a terminal works on the Mac Scranton runs on."}, status_code=400)
    session = _sc_tmux_session(name)
    if not _re.fullmatch(r"[A-Za-z0-9_.-]+", session):
        return JSONResponse({"error": "unexpected terminal name"}, status_code=400)
    tmux = _sh.which("tmux") or "tmux"
    # quoted: zsh reads a bare "=name" as "the path of command name" (Lu, 11-10: "agentchattr-visintern not found")
    script = f'tell application "Terminal" to do script "{tmux} attach -t \\"={session}\\""\ntell application "Terminal" to activate'
    r = await asyncio.to_thread(_sp.run, ["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return JSONResponse({"error": (r.stderr or "Terminal didn't open").strip()[:200]}, status_code=500)
    return JSONResponse({"ok": True})


@app.post("/api/scranton/teammate/{name}")
async def scranton_teammate_update(name: str, request: Request):
    """Change model / permissions / autostart, or start / stop / restart."""
    body = await request.json()
    action = str(body.get("action", ""))
    try:
        if action == "set":
            entry = _sc_team.set_override(name, str(body.get("key", "")), body.get("value"), config)
            await broadcast_team_changed()
            return JSONResponse({"ok": True, "saved": entry, "restart_needed": agents.is_available(name)})
        if action == "plan":   # back to its plan from the backup API key
            _sc_keys.end_api(name)
            action = "restart"
        if action in ("stop", "restart"):
            await asyncio.to_thread(_sc_team.stop, name, config, _scranton_ops.RUN_DIR)
            # Free the name now, so the restarted agent comes back as itself (not "pm-2").
            _scranton_ops._starting.pop(name, None)
            import mcp_bridge
            for inst in [n for n, i in list(registry._instances.items()) if n == name or i.base == name]:
                if registry.deregister(inst):
                    mcp_bridge.purge_identity(inst)
                    registry.clean_renames_for(inst)
        if action in ("start", "restart"):
            res = await asyncio.to_thread(_scranton_ops.ensure_running, [name], config)
            if name in res.get("failed", {}):
                return JSONResponse({"ok": False, "error": res["failed"][name]})
        if action not in ("start", "stop", "restart"):
            return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
        return JSONResponse({"ok": True})
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.get("/api/scranton/agents/library")
async def scranton_agent_library():
    return JSONResponse(_sc_team.library(config))


@app.get("/api/scranton/agents/new")
async def scranton_agent_new_options():
    return JSONResponse({"folders": _sc_team.project_folders(config), "avatars": _sc_team.avatars(),
                         "models": {p: _sc_team.models_for(p) for p in ("claude", "codex", "cursor")},
                         "channels": [c for c in room_settings.get("channels", []) if not c.startswith("dm-")]})


@app.post("/api/scranton/agents")
async def scranton_agents_change(request: Request):
    body = await request.json()
    action = str(body.get("action", ""))
    try:
        if action == "add":
            a = _sc_team.add_agent(body, config)
            registry.seed({a["handle"]: config["agents"][a["handle"]]})
            _on_registry_change()
            chans = [c for c in (body.get("channels") or []) if c in room_settings.get("channels", [])]
            for c in chans:
                _add_members(c, [a["handle"]])
            _save_settings()
            await broadcast_settings()
            await broadcast_team_changed()
            res = await asyncio.to_thread(_scranton_ops.ensure_running, [a["handle"]], config)
            return JSONResponse({"ok": True, "agent": a, "start": res})
        if action == "restore":
            name = str(body.get("name", ""))
            await asyncio.to_thread(_sc_team.restore_agent, name, config)
            registry.seed({name: config["agents"][name]})
            _on_registry_change()
            await broadcast_settings()
            await broadcast_team_changed()
            return JSONResponse({"ok": True})
        if action == "delete":
            name = str(body.get("name", ""))
            await asyncio.to_thread(_sc_team.delete_agent, name, config, _scranton_ops.RUN_DIR)
            for ch, ns in (room_settings.get("channel_members") or {}).items():
                if name in ns:
                    ns.remove(name)
            _save_settings()
            _on_registry_change()
            await broadcast_settings()
            await broadcast_team_changed()
            return JSONResponse({"ok": True})
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)


async def broadcast_team_changed():
    data = json.dumps({"type": "scranton_team_changed"})
    for c in list(ws_clients):
        try:
            await c.send_text(data)
        except Exception:
            pass


@app.get("/api/scranton/search")
async def scranton_search(q: str = "", limit: int = 30):
    """Search message text and sender across all channels, newest first."""
    needle = (q or "").strip().lower()[:200]
    if not needle:
        return JSONResponse([])
    limit = max(1, min(int(limit or 30), 100))
    hits = []
    for m in reversed(store.get_since(-1)):
        if m.get("sender") == "system" or m.get("type") == "system":
            continue
        if needle in str(m.get("text", "")).lower() or needle in str(m.get("sender", "")).lower():
            hits.append({k: m.get(k) for k in ("id", "sender", "text", "channel", "time", "timestamp", "reply_to")})
            if len(hits) >= limit:
                break
    return JSONResponse(hits)


@app.get("/api/roles")
async def get_roles():
    """Get all agent roles."""
    import mcp_bridge
    return mcp_bridge.get_all_roles()


@app.post("/api/roles/{agent_name}")
async def set_agent_role(agent_name: str, request: Request):
    """Set or clear an agent's role."""
    import mcp_bridge
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    role = body.get("role", "").strip()
    mcp_bridge.set_role(agent_name, role)
    await broadcast_status()
    return JSONResponse({"ok": True, "role": role})


# --- Rules API ---

@app.get("/api/rules")
async def get_rules():
    """Get all rules (all states)."""
    return JSONResponse(rules.list_all())


@app.get("/api/rules/active")
async def get_active_rules():
    """Get compact active rules for agent injection."""
    data = rules.active_list()
    data["refresh_interval"] = room_settings.get("rules_refresh_interval", 10)
    return JSONResponse(data)


@app.post("/api/rules/remind")
async def remind_agents():
    """Set remind flag — agents get rules on next trigger."""
    rules.set_remind()
    remind_data = json.dumps({"type": "rules_remind", "data": {}})
    for client in list(ws_clients):
        try:
            await client.send_text(remind_data)
        except Exception:
            pass
    return JSONResponse({"ok": True})


@app.post("/api/rules/agent_sync/{agent_name}")
async def report_rule_sync(agent_name: str, request: Request):
    """Wrapper reports that an agent has seen rules at a given epoch."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    epoch = body.get("epoch", 0)
    rules.report_agent_sync(agent_name, epoch)
    # Clear remind flag once any agent has seen the updated rules
    rules.clear_remind()
    return JSONResponse({"ok": True})


@app.get("/api/rules/freshness")
async def get_rules_freshness():
    """Get per-agent sync status."""
    return JSONResponse(rules.agent_freshness())


@app.post("/api/register")
async def register_agent(request: Request):
    """Wrapper calls this to register a new agent instance."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    base = body.get("base", "")
    label = body.get("label")
    if not base:
        return JSONResponse({"error": "base is required"}, status_code=400)
    result = registry.register(base, label)
    if result is None:
        return JSONResponse({"error": f"unknown base: {base}"}, status_code=400)
    # Touch presence so the instance doesn't immediately time out
    import mcp_bridge
    with mcp_bridge._presence_lock:
        mcp_bridge._presence[result["name"]] = __import__("time").time()
    # If slot 1 was renamed (e.g. "claude" → "claude-1"), migrate state
    renamed = result.pop("_renamed_slot1", None)
    if renamed:
        mcp_bridge.migrate_identity(renamed["old"], renamed["new"])
        store.rename_sender(renamed["old"], renamed["new"])
        _migrate_agent_last_channel(renamed["old"], renamed["new"])
        if _event_loop:
            rename_event = json.dumps({
                "type": "agent_renamed",
                "old_name": renamed["old"],
                "new_name": renamed["new"],
            })
            asyncio.run_coroutine_threadsafe(_broadcast(rename_event), _event_loop)
    # Broadcast pending_instance event so UI can show naming lightbox
    if result.get("state") == "pending" and _event_loop:
        pending_event = json.dumps({
            "type": "pending_instance",
            "name": result["name"],
            "base": base,
            "label": result.get("label", result["name"]),
            "color": result.get("color", "#888"),
        })
        asyncio.run_coroutine_threadsafe(_broadcast(pending_event), _event_loop)
    return JSONResponse(result)


@app.post("/api/deregister/{name}")
async def deregister_agent(name: str, request: Request):
    """Wrapper calls this on shutdown to remove its instance."""
    auth_inst = _resolve_authenticated_agent(request)
    presented_token = _extract_agent_token(request)
    if presented_token and not auth_inst:
        return JSONResponse({"error": "stale_session"}, status_code=409)
    if auth_inst:
        name = auth_inst["name"]
    elif registry and registry.is_agent_family(name):
        return JSONResponse({"error": "authenticated agent session required"}, status_code=403)

    result = registry.deregister(name)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    # Clean up runtime state (presence, activity, cursors, rename chains)
    import mcp_bridge
    mcp_bridge.purge_identity(name)
    registry.clean_renames_for(name)
    # If the remaining instance was renamed back (e.g. "claude-1" → "claude"), migrate state
    renamed = result.pop("_renamed_back", None)
    if renamed:
        mcp_bridge.migrate_identity(renamed["old"], renamed["new"])
        store.rename_sender(renamed["old"], renamed["new"])
        _migrate_agent_last_channel(renamed["old"], renamed["new"])
        if _event_loop:
            rename_event = json.dumps({
                "type": "agent_renamed",
                "old_name": renamed["old"],
                "new_name": renamed["new"],
            })
            asyncio.run_coroutine_threadsafe(_broadcast(rename_event), _event_loop)
    return JSONResponse({"ok": True})


@app.post("/api/label/{name}")
async def rename_agent_label(name: str, request: Request):
    """Rename an agent (human-initiated from UI). Changes identity + label."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    label = body.get("label", "").strip()
    if not label:
        return JSONResponse({"error": "label is required"}, status_code=400)

    import re as _re
    new_id = _re.sub(r'[^a-z0-9-]', '', label.lower().replace(' ', '-')).strip('-')
    if not new_id:
        new_id = name

    if new_id == name:
        # Same ID — label-only change
        if registry.set_label(name, label):
            return JSONResponse({"ok": True})
        return JSONResponse({"error": "not found"}, status_code=404)

    result = registry.rename(name, new_id, label)
    if isinstance(result, str):
        # Rename failed — try label-only as fallback
        if registry.set_label(name, label):
            return JSONResponse({"ok": True, "warning": result})
        return JSONResponse({"error": result}, status_code=400)

    import mcp_bridge
    mcp_bridge.migrate_identity(name, new_id)
    # Update sender on all historical messages
    store.rename_sender(name, new_id)
    _migrate_agent_last_channel(name, new_id)
    return JSONResponse({"ok": True, "new_name": new_id})


_sc_doing: dict[str, str] = {}
import scranton_report as _sc_report  # noqa: E402
import scranton_backup as _sc_backup  # noqa: E402
import scranton_presence as _sc_presence  # noqa: E402
import scranton_shortcuts as _sc_shortcuts  # noqa: E402
import scranton_grok as _sc_grok  # noqa: E402


async def _broadcast_json(payload: dict):
    data = json.dumps(payload)
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


@app.post("/api/heartbeat/{agent_name}")
async def heartbeat(agent_name: str, request: Request):
    """Wrapper calls this to keep presence alive and report activity.

    Returns the canonical name from the registry so the wrapper can
    detect renames (e.g. claim renamed 'claude-2' to 'claude-music').
    """
    import mcp_bridge
    auth_inst = _resolve_authenticated_agent(request)
    presented_token = _extract_agent_token(request)
    if presented_token and not auth_inst:
        return JSONResponse({"error": "stale_session"}, status_code=409)
    if registry and registry.is_agent_family(agent_name) and not auth_inst:
        return JSONResponse({"error": "authenticated agent session required"}, status_code=403)

    current_name = auth_inst["name"] if auth_inst else agent_name
    with mcp_bridge._presence_lock:
        mcp_bridge._presence[current_name] = __import__("time").time()
    # Optional activity report from wrapper's terminal monitor
    _activity_changed = False
    try:
        body = await request.json()
        if "active" in body:
            active_val = bool(body["active"])
            was_active = mcp_bridge._activity.get(current_name, False)
            mcp_bridge.set_active(current_name, active_val)
            _activity_changed = was_active != active_val
            if active_val:
                _sc_idle_since.pop(current_name, None)
            else:
                _sc_idle_since.setdefault(current_name, __import__("time").time())
        if "active" in body:
            _sc_report.note_active(current_name, bool(body["active"]))
        # Scranton: a few words on what it's doing ("Reading page.tsx"), for "X is working · …"
        if "doing" in body:
            doing = str(body.get("doing") or "")[:80] if body.get("active") else ""
            if _sc_doing.get(current_name, "") != doing:
                _sc_doing[current_name] = doing
                await _broadcast_json({"type": "scranton_doing", "agent": current_name, "text": doing})
    except Exception:
        pass  # No body = plain heartbeat
    # Immediately broadcast on activity state change (don't wait for background checker)
    if _activity_changed:
        await broadcast_status()
    # Return canonical name so wrapper can track renames
    resp = {"ok": True, "name": current_name}
    if registry:
        # Follow rename chain (e.g. claude-2 was renamed to claude-music)
        canonical = registry.resolve_name(current_name)
        inst = registry.get_instance(canonical)
        # If rename chain didn't help, try family-based lookup
        # (handles case where _renames was cleared by server restart but
        # the instance was claimed/renamed via MCP)
        if not inst:
            base = current_name.split("-")[0] if "-" in current_name else current_name
            family_inst = registry.get_family_instance(base)
            if family_inst:
                inst = family_inst
                canonical = inst["name"]
        if inst:
            resp["name"] = inst["name"]
            resp["pending"] = inst.get("state") == "pending"
            # Also update presence under the canonical name
            if canonical != current_name:
                now = __import__("time").time()
                with mcp_bridge._presence_lock:
                    mcp_bridge._presence[canonical] = now
    return resp


# --- Open agent session in terminal ---

@app.get("/api/platform")
async def get_platform():
    """Return the server's platform so the web UI can match path formats."""
    import sys
    return JSONResponse({"platform": sys.platform})


@app.post("/api/open-path")
async def open_path(body: dict):
    """Open a file or directory in the native file manager.

    Cross-platform: Explorer on Windows, Finder on macOS, xdg-open on Linux.

    Security note: This endpoint is intended for local-only use (127.0.0.1).
    Do not expose this server on a public network without additional access controls.
    """
    import subprocess
    import sys

    path = body.get("path", "")
    if not path:
        return JSONResponse({"error": "no path"}, status_code=400)

    p = Path(path)
    try:
        if sys.platform == "win32":
            if p.is_file():
                subprocess.Popen(["explorer", "/select,", str(p)])
            elif p.is_dir():
                subprocess.Popen(["explorer", str(p)])
            else:
                return JSONResponse({"error": "path not found"}, status_code=404)
        elif sys.platform == "darwin":
            if p.is_file():
                subprocess.Popen(["open", "-R", str(p)])
            elif p.is_dir():
                subprocess.Popen(["open", str(p)])
            else:
                return JSONResponse({"error": "path not found"}, status_code=404)
        else:
            # Linux — xdg-open opens the containing folder for files
            if p.is_file():
                subprocess.Popen(["xdg-open", str(p.parent)])
            elif p.is_dir():
                subprocess.Popen(["xdg-open", str(p)])
            else:
                return JSONResponse({"error": "path not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"ok": True})


# Serve uploaded images
# --- Sessions API ---

@app.get("/api/sessions/templates")
async def get_session_templates():
    if not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    return JSONResponse(session_store.get_templates())


@app.get("/api/sessions/active")
async def get_active_session(channel: str = "general"):
    if not session_engine:
        return JSONResponse(None)
    session = session_engine.get_active(channel)
    return JSONResponse(session)


@app.get("/api/sessions/active-all")
async def get_all_active_sessions():
    if not session_engine:
        return JSONResponse([])
    return JSONResponse(session_engine.list_active())


@app.post("/api/sessions/start")
async def start_session(request: Request):
    if not session_engine or not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    body = await request.json()
    template_id = body.get("template_id", "")
    draft_message_id = body.get("draft_message_id")
    channel = body.get("channel", "general")
    cast = body.get("cast", {})
    goal = body.get("goal", "")
    started_by = body.get("started_by", "user")

    # If running from a draft, load the inline template from message metadata
    tmpl = None
    if draft_message_id:
        draft_msg = store.get_by_id(int(draft_message_id))
        if not draft_msg:
            return JSONResponse({"error": "draft message not found"}, status_code=404)
        meta = draft_msg.get("metadata", {})
        if not meta.get("valid"):
            return JSONResponse({"error": "draft is not valid"}, status_code=400)
        tmpl = meta.get("template")
        if not tmpl:
            return JSONResponse({"error": "draft has no template"}, status_code=400)
        # Register as a temporary template
        template_id = tmpl.get("id", f"draft-{draft_message_id}")
        tmpl["id"] = template_id
        tmpl["is_custom"] = True
        session_store._templates[template_id] = tmpl

    # Validate template exists
    if not tmpl:
        tmpl = session_store.get_template(template_id)
    if not tmpl:
        return JSONResponse({"error": f"unknown template: {template_id}"}, status_code=400)

    # Auto-fill cast from available agents if not fully provided
    if not cast:
        online = registry.get_active_names() if registry else []
        roles = tmpl.get("roles", [])
        cast = _auto_cast(roles, online, started_by)
        if not cast:
            return JSONResponse(
                {"error": "not enough agents online to fill all roles"},
                status_code=400,
            )

    session = session_engine.start_session(template_id, channel, cast, started_by, goal)
    if not session:
        return JSONResponse({"error": "could not start session (one may already be active)"}, status_code=409)

    # Add start banner to chat (only after confirmed success)
    store.add(
        sender="system",
        text=f"Session started: {tmpl.get('name', template_id)}",
        msg_type="session_start",
        channel=channel,
        metadata={"template_id": template_id, "goal": goal, "session_id": session["id"]},
    )
    session_engine.emit_current_phase_banner(session)

    return JSONResponse(session)


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: int):
    if not session_engine:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    session = session_engine.end_session(session_id)
    if not session:
        return JSONResponse({"error": "session not found or already ended"}, status_code=404)

    # Banner is added by _on_session_change("interrupt", ...) callback
    return JSONResponse(session)


@app.post("/api/sessions/request-draft")
async def request_session_draft(request: Request):
    """Ask an agent to design a session template. Called by the 'Design a session' UI."""
    body = await request.json()
    agent_name = body.get("agent", "").strip()
    description = body.get("description", "").strip()
    channel = body.get("channel", "general")
    sender = body.get("sender", "user")
    if not agent_name or not description:
        return JSONResponse({"error": "agent and description required"}, status_code=400)

    mention_str = f"@{agent_name}"
    store.add(
        "system",
        f"Requested session draft from {mention_str}. Wait for a proposal.",
        channel=channel,
    )
    store.add(
        sender,
        f"{mention_str} Design a session workflow for: **{description}**\n\n"
        "Respond with a single chat message containing a fenced JSON code block with this exact structure:\n"
        "```session\n"
        '{"name": "...", "description": "...", "roles": ["role1", "role2", ...], '
        '"phases": [{"name": "...", "participants": ["role1"], "prompt": "...", "is_output": false}, ...]}\n'
        "```\n"
        "Rules: max 6 roles, max 6 phases, max 4 participants per phase, max 200 chars per prompt. "
        "Mark exactly one phase as `is_output: true` (the final deliverable). "
        f"Keep it focused and sequential. Use the chat_send tool to post your response in the #{channel} channel. "
        "Do NOT respond only in your terminal.",
        channel=channel,
        msg_type="session_request",
        metadata={"session_request": True, "mentions": [f"@{agent_name}"], "request": description},
    )
    return JSONResponse({"ok": True})


@app.post("/api/sessions/save-draft")
async def save_draft(request: Request):
    if not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    body = await request.json()
    msg_id = body.get("message_id")
    if not msg_id:
        return JSONResponse({"error": "message_id required"}, status_code=400)
    msg = store.get_by_id(int(msg_id))
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    meta = msg.get("metadata", {})
    if not meta.get("valid"):
        return JSONResponse({"error": "draft is not valid"}, status_code=400)
    tmpl = meta.get("template")
    if not tmpl:
        return JSONResponse({"error": "no template in draft"}, status_code=400)

    tmpl.setdefault("id", f"custom-{msg_id}")
    session_store.save_custom_template(tmpl)
    return JSONResponse({"ok": True, "template_id": tmpl["id"]})


@app.delete("/api/sessions/templates/{template_id}")
async def delete_session_template(template_id: str):
    if not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    deleted = session_store.delete_custom_template(template_id)
    if not deleted:
        return JSONResponse({"error": "template not found or not custom"}, status_code=404)
    return JSONResponse({"ok": True, "template_id": template_id})


def _auto_cast(roles: list[str], online_agents: list[str], started_by: str) -> dict:
    """Auto-assign roles to available agents. Returns empty dict if not enough agents."""
    cast = {}
    available = list(online_agents)

    for role in roles:
        if not available:
            # Reuse agents if we run out (one agent, multiple roles)
            available = list(online_agents)
        if not available:
            return {}
        agent = available.pop(0)
        cast[role] = agent

    return cast


# --- Version check (GitHub release notifier) ---

_version_cache: dict = {"data": None, "fetched_at": 0.0}
_VERSION_CACHE_TTL = 1800  # 30 minutes


def _read_local_version() -> str:
    """Read version from VERSION file in project root."""
    vfile = Path(__file__).parent / "VERSION"
    try:
        return vfile.read_text().strip()
    except Exception:
        return ""


def _detect_install_kind() -> str:
    """Detect how this copy was installed: official_git, fork, or unknown."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).parent,
        )
        url = result.stdout.strip().lower()
        if "bcurts/agentchattr" in url:
            return "official_git"
        elif url:
            return "fork"
    except Exception:
        pass
    return "unknown"


def _fetch_latest_release() -> dict | None:
    """Fetch latest release from GitHub API, with 30-min cache."""
    import time
    import urllib.request

    now = time.time()
    if _version_cache["data"] and (now - _version_cache["fetched_at"]) < _VERSION_CACHE_TTL:
        return _version_cache["data"]

    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/bcurts/agentchattr/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "agentchattr"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result = {
                "tag": data.get("tag_name", ""),
                "url": data.get("html_url", ""),
            }
            _version_cache["data"] = result
            _version_cache["fetched_at"] = now
            return result
    except Exception:
        return _version_cache.get("data")


def _compare_versions(current: str, latest_tag: str) -> str:
    """Compare version strings. Returns 'behind', 'current', or 'unknown'."""
    # Strip leading 'v' from tag
    latest = latest_tag.lstrip("v")
    if not current or not latest:
        return "unknown"
    try:
        from packaging.version import Version
        if Version(current) < Version(latest):
            return "behind"
        return "current"
    except Exception:
        return "unknown"


@app.get("/api/version_check")
async def version_check():
    """Check for newer releases on GitHub."""
    current = _read_local_version()
    # Scranton is a private fork: don't contact api.github.com about upstream
    # releases. Pull upstream changes deliberately instead.
    return JSONResponse({"current": current, "latest": "", "state": "unknown", "url": ""})
    loop = asyncio.get_event_loop()
    release = await loop.run_in_executor(None, _fetch_latest_release)

    if not release or not release.get("tag"):
        return JSONResponse({"current": current, "latest": "", "state": "unknown", "url": ""})

    latest_tag = release["tag"]
    install_kind = _detect_install_kind()
    comparison = _compare_versions(current, latest_tag)

    if comparison == "behind":
        if install_kind == "official_git":
            state = "update_available"
        elif install_kind == "fork":
            state = "upstream_update"
        else:
            state = "unknown"
    elif comparison == "current":
        state = "current"
    else:
        state = "unknown"

    return JSONResponse({
        "current": current,
        "latest": latest_tag,
        "state": state,
        "url": release.get("url", ""),
    })


_THUMB_WIDTHS = (480, 960)   # what the chat shows (300 px wide, 2x screens); full size opens on click
_UPLOAD_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}   # upload names are random and never reused


def _thumbnail(filepath: Path, upload_dir: Path, w: int):
    """A smaller copy of an uploaded picture for the chat (Lu, 11-10: the phone fetched 179 MB of
    full-size images on every load). Made once, kept in uploads/.thumbs. None if it can't be made."""
    if filepath.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return None   # SVG and GIF (may be animated) are served as they are
    out = upload_dir.resolve() / ".thumbs" / f"{filepath.stem}-{w}.webp"
    if out.is_file() and out.stat().st_mtime >= filepath.stat().st_mtime:
        return out
    try:
        from PIL import Image
        with Image.open(filepath) as im:
            if im.width <= w:
                return None   # already small: the original is the thumbnail
            im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
            im.thumbnail((w, w * 4))
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            im.save(tmp, "WEBP", quality=82, method=4)
            tmp.replace(out)
        return out
    except Exception:
        return None   # Pillow missing or an odd file: fall back to the original


@app.get("/uploads/{filename}")
async def serve_upload(filename: str, w: int | None = None):
    upload_dir = Path(config.get("images", {}).get("upload_dir", "./uploads"))
    filepath = (upload_dir / filename).resolve()
    if not filepath.is_relative_to(upload_dir.resolve()):
        return JSONResponse({"error": "invalid path"}, status_code=400)
    if filepath.is_file() and w in _THUMB_WIDTHS and filepath.suffix.lower() in IMAGE_UPLOAD_EXTS:
        thumb = await asyncio.to_thread(_thumbnail, filepath, upload_dir, w)
        if thumb is not None:
            return FileResponse(thumb, media_type="image/webp", headers={"X-Content-Type-Options": "nosniff", **_UPLOAD_CACHE})
    if filepath.is_file():
        if filepath.suffix.lower() == ".svg":
            # an SVG opened in its own tab would run its scripts on Scranton's origin
            return FileResponse(filepath, media_type="image/svg+xml",
                                headers={"Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
                                         "X-Content-Type-Options": "nosniff"})
        if filepath.suffix.lower() in IMAGE_UPLOAD_EXTS:
            return FileResponse(filepath, headers={"X-Content-Type-Options": "nosniff", **_UPLOAD_CACHE})
        # Documents are downloads, never executable same-origin pages.
        return FileResponse(filepath, media_type="application/octet-stream",
                            filename=filepath.name,
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
    return JSONResponse({"error": "not found"}, status_code=404)


# ---------------------------------------------------------------- live terminal (Lu, 11-10: "embed 进去，像 Cursor")
@app.websocket("/ws/term/{name}")
async def scranton_term_ws(websocket: WebSocket, name: str):
    """A real, typeable view of a teammate's terminal: `tmux attach` to its session in a pty,
    bytes both ways. Same token and origin check as /ws. Closing the view detaches only;
    the teammate keeps running."""
    token = websocket.query_params.get("token", "")
    ws_origin = getattr(websocket, "headers", {}).get("origin")
    if ws_origin and ws_origin.rstrip("/") not in getattr(sys.modules[__name__], "allowed_ws_origins", set()):
        token = ""
    await websocket.accept()
    if token != session_token or name not in (config or {}).get("agents", {}):
        await websocket.close(code=4003, reason="forbidden")
        return
    import fcntl, pty, shutil as _sh, signal, struct, subprocess as _sp, termios
    session = _sc_tmux_session(name)
    tmux = _sh.which("tmux") or "tmux"
    if _sp.run([tmux, "has-session", "-t", f"={session}"], capture_output=True).returncode != 0:
        await websocket.send_bytes(f"\r\n  {name} isn't running. Start it, then open this again.\r\n".encode())
        await websocket.close()
        return
    # tmux's green status bar fights the design system and repeats what the tab already says
    # (Lu, 11-11). Session option only: her own tmux sessions keep theirs.
    _sp.run([tmux, "set-option", "-t", f"={session}", "status", "off"], capture_output=True)
    master, slave = pty.openpty()

    def size(cols: int, rows: int):
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", max(10, min(rows, 200)), max(20, min(cols, 400)), 0, 0))
        except OSError:
            pass
    size(100, 30)
    env = {**os.environ, "TERM": "xterm-256color"}
    env.pop("TMUX", None)
    proc = _sp.Popen([tmux, "attach", "-t", f"={session}"], stdin=slave, stdout=slave, stderr=slave,
                     env=env, start_new_session=True, close_fds=True)
    os.close(slave)
    os.set_blocking(master, False)
    loop = asyncio.get_running_loop()
    out: asyncio.Queue = asyncio.Queue()

    def readable():
        try:
            data = os.read(master, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        out.put_nowait(data)
    loop.add_reader(master, readable)

    async def pump_out():
        while True:
            data = await out.get()
            if not data:
                break
            await websocket.send_bytes(data)
        try:
            await websocket.close()
        except Exception:
            pass
    sender = asyncio.create_task(pump_out())
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text")
            if text is None:
                continue
            try:
                ev = json.loads(text)
            except ValueError:
                continue
            if ev.get("t") == "in" and isinstance(ev.get("d"), str):
                os.write(master, ev["d"].encode("utf-8", "replace"))
            elif ev.get("t") == "size":
                size(int(ev.get("c") or 100), int(ev.get("r") or 30))
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        loop.remove_reader(master)
        sender.cancel()
        try:
            os.killpg(proc.pid, signal.SIGHUP)   # detach this view only; the tmux session stays
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        os.close(master)



# ---------------------------------------------------------------- backup API keys (Lu, 11-10)
def _api_backup_on() -> bool:
    """Lu's switch (11-11): keys stay saved, but nobody moves to one while it's off (the default)."""
    return bool(room_settings.get("api_backup_enabled", False))


def _api_allowed(provider: str) -> bool:
    """The switch, or Lu picked "API first" for this plan when it reached 98% (until it resets)."""
    return _api_backup_on() or _sc_qa().api_ok(provider)


@app.get("/api/scranton/api-keys")
async def scranton_api_keys_get():
    return JSONResponse({"keys": _sc_keys.summary(), "on_api": _sc_keys.all_on_api(), "enabled": _api_backup_on()})


@app.post("/api/scranton/api-keys")
async def scranton_api_keys_set(request: Request):
    body = await request.json()
    if "enabled" in body and "provider" not in body:
        room_settings["api_backup_enabled"] = bool(body.get("enabled"))
        _save_settings()
        if not _api_backup_on():
            await _sc_api_heal()
        return JSONResponse({"ok": True, "enabled": _api_backup_on(), "keys": _sc_keys.summary(), "on_api": _sc_keys.all_on_api()})
    err = _sc_keys.set_key(str(body.get("provider", "")), str(body.get("key", "")))
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    return JSONResponse({"ok": True, "keys": _sc_keys.summary()})


async def _sc_restart_quiet(name: str) -> None:
    await asyncio.to_thread(_sc_team.stop, name, config, _scranton_ops.RUN_DIR)
    _scranton_ops._starting.pop(name, None)
    import mcp_bridge
    for inst in [n for n, i in list(registry._instances.items()) if n == name or i.base == name]:
        if registry.deregister(inst):
            mcp_bridge.purge_identity(inst)
            registry.clean_renames_for(inst)
    await asyncio.to_thread(_scranton_ops.ensure_running, [name], config)


@app.post("/api/scranton/api-fallback")
async def scranton_api_fallback(request: Request):
    """A teammate's wrapper says its plan is out. With a backup key for that app it restarts on
    the key and says so; otherwise the wrapper reports the limit as before."""
    auth = request.headers.get("authorization", "")
    inst = registry.resolve_token(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
    if not inst:
        return JSONResponse({"switching": False}, status_code=403)
    base = inst.get("base") or inst["name"]
    cfg = (config or {}).get("agents", {}).get(base, {})
    provider = _sc_keys.provider_of_command(cfg.get("command", ""))
    # Only when the real numbers say the plan is out (11-11: pm was moved to a key with no money
    # because it had quoted "hit its usage limit" in a reply, with 77% of the week used).
    if not _api_allowed(provider or ""):
        return JSONResponse({"switching": False, "off": True})
    usage = _sc_quota.provider_usage(provider or "", _current_model(base)[1])
    if not usage or usage["pct"] < 99:
        return JSONResponse({"switching": False, "pct": (usage or {}).get("pct")})
    if not provider or _sc_keys.on_api(base):
        return JSONResponse({"switching": False})
    if not _sc_keys.start_api(base, provider):
        # No key: Lu's "then another app" still applies.
        moved = await _sc_qa_move_if_planned(base, provider, str((await request.json()).get("channel") or "general"))
        return JSONResponse({"switching": moved})
    body = await request.json()
    app_name = {"claude": "Claude", "codex": "ChatGPT"}[provider]
    store.add(inst["name"], f"My {app_name} plan has hit its limit, so I'm carrying on with the backup API key "
                            f"(pay per use) and will go back to the plan in about 5 hours.",
              channel=str(body.get("channel") or "general"),
              reply_to=body.get("thread") if isinstance(body.get("thread"), int) else None)
    asyncio.create_task(_sc_restart_quiet(base))
    return JSONResponse({"switching": True})


# ---------------------------------------------------------------- is the plan really out? (Lu, 11-11)
# The wrapper sees "limit" on a teammate's screen and asks here before stopping it. A warning is not
# the end: the real numbers decide (Agent Monitor's usage.json). If only this model's quota is out
# (Cursor's "Other models", Gemini Argon), it carries on with a model that still has room and goes
# back when that quota resets. Only then the backup API key, and only then "I stopped".
_MODEL_FB = Path(__file__).parent / "data" / "model_fallback.json"
import time  # noqa: E402  (used by the limit check below)


def _model_fb_load() -> dict:
    try:
        d = json.loads(_MODEL_FB.read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _model_fb_save(d: dict) -> None:
    _MODEL_FB.parent.mkdir(parents=True, exist_ok=True)
    _MODEL_FB.write_text(json.dumps(d, indent=1), "utf-8")


def _current_model(base: str) -> tuple[str, str]:
    cfg = (config or {}).get("agents", {}).get(base, {})
    provider = _sc_team.provider_of(cfg.get("command", ""))
    ov = _sc_team.load_overrides()
    model = (ov.get(base, {}) or {}).get("model") or ((ov.get("_added", {}) or {}).get(base, {}) or {}).get("model") \
        or cfg.get("model") or ((ov.get("_defaults") or {}).get(provider) or "")
    return provider, str(model or "")


def _model_label(m: str) -> str:
    return (m or "the default model").replace("-", " ").title().replace("Gpt", "GPT")


_LIMIT_UNKNOWN: dict[str, float] = {}   # base -> when a limit was first seen with no numbers to check


def _limit_verdict(base: str, problem: str, usage: dict | None, now: float | None = None) -> str:
    """'ignore' or 'go on' (to model fallback / report). Lu, 11-11: "reach limit 不是不能走，要用到
    100% 才可以" — words on a screen are not a stop. With numbers: under 99% is room, keep working.
    Without numbers: not on the first sighting; only if it's still there on the check 10+ minutes later."""
    now = time.time() if now is None else now
    if problem != "limit":
        return "go on"
    if usage:
        _LIMIT_UNKNOWN.pop(base, None)
        return "ignore" if usage["pct"] < 99 else "go on"
    first = _LIMIT_UNKNOWN.get(base)
    if not first or now - first > 3600:
        _LIMIT_UNKNOWN[base] = now
        return "ignore"
    return "go on" if now - first >= 480 else "ignore"


def _limit_log(base: str, problem: str, usage: dict | None, verdict: str, screen: str) -> None:
    """One line per check, with the screen lines that set it off, so a wrong stop can be traced."""
    try:
        tail = [l.strip() for l in screen.splitlines() if l.strip()][-8:]
        line = json.dumps({"at": time.strftime("%m-%d %H:%M:%S"), "who": base, "problem": problem,
                           "pct": (usage or {}).get("pct"), "verdict": verdict, "screen": tail}, ensure_ascii=False)
        log = Path((config or {}).get("server", {}).get("data_dir", "./data")) / "logs" / "limit-check.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


@app.post("/api/scranton/limit-check")
async def scranton_limit_check(request: Request):
    auth = request.headers.get("authorization", "")
    inst = registry.resolve_token(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
    if not inst:
        return JSONResponse({"action": "report"}, status_code=403)
    base = inst.get("base") or inst["name"]
    body = await request.json()
    problem = str(body.get("problem") or "")
    screen = str(body.get("text") or "")[-3000:]
    place = {"channel": str(body.get("channel") or "general"),
             "reply_to": body.get("thread") if isinstance(body.get("thread"), int) else None}
    provider, model = _current_model(base)
    # The backup key has no money: go back to the plan (it has room, or we'd not be here twice).
    if problem == "api_credit":
        if _sc_keys.on_api(base) and await _sc_qa_move_if_planned(base, _sc_keys.on_api(base).get("provider") or provider,
                                                                  place["channel"], after_api=True):
            _sc_keys.end_api(base)
            return JSONResponse({"action": "switched"})
        if _sc_keys.on_api(base):
            _sc_keys.end_api(base)
            store.add(inst["name"], "The backup API key has no credit left, so I'm going back to the plan. "
                                    "Add funds with the provider, or remove the key in Settings → Connections.",
                      channel=place["channel"], reply_to=place["reply_to"])
            asyncio.create_task(_sc_restart_quiet(base))
            return JSONResponse({"action": "switched"})
        return JSONResponse({"action": "report"})
    usage = _sc_quota.provider_usage(provider, model)
    fb = _sc_quota.model_fallback(provider, model)
    if problem == "model_limit" and not (fb and fb != model):
        problem = "limit"   # no other model to move to (Claude): same rule as the plan
    verdict = _limit_verdict(base, problem, usage)
    _limit_log(base, problem, usage, verdict, screen)
    if verdict == "ignore":
        return JSONResponse({"action": "ignore", "pct": (usage or {}).get("pct")})
    # 1b. Lu picked "move to another app" at 98%: do it now that it's really out.
    if problem == "limit" and usage and usage["pct"] >= 99 and \
            (_sc_qa().approved.get(provider) or {}).get("mode") == "move":
        if await _sc_qa_move_if_planned(base, provider, place["channel"]):
            return JSONResponse({"action": "switched"})
    # 2. Only this model is out: same plan, another model.
    if fb and fb != model and base in (config or {}).get("agents", {}):
        until = _sc_quota.reset_from_text(screen) or (usage or {}).get("resets") or (time.time() + 5 * 3600)
        d = _model_fb_load()
        d[base] = {"from": model, "to": fb, "since": time.time(), "until": float(until)}
        _model_fb_save(d)
        _sc_team.set_override(base, "model", fb, config)
        when = time.strftime("%m-%d %H:%M", time.localtime(float(until)))
        store.add(inst["name"], f"{_model_label(model)} has used up its quota, but the plan still has room on other models: "
                                f"I'm carrying on with {_model_label(fb)} and will switch back after it resets ({when}).",
                  channel=place["channel"], reply_to=place["reply_to"])
        await broadcast_team_changed()
        asyncio.create_task(_sc_restart_quiet(base))
        return JSONResponse({"action": "switched", "model": fb})
    # The backup key (money) only when the numbers say the plan is really out. A screen saying
    # "limit" without numbers behind it has been wrong too often (11-10, 11-11) to spend money on.
    parts = [_model_label(model)] if model else []
    if usage:
        parts.append(f"{usage['label'] or 'quota'} {usage['pct']:.0f}% used")
        if usage.get("resets"):
            parts.append("resets " + time.strftime("%m-%d %H:%M", time.localtime(float(usage["resets"]))))
    else:
        parts.append("no usage numbers, going by the screen")
    return JSONResponse({"action": "report", "pct": (usage or {}).get("pct"), "detail": ", ".join(parts),
                         "api_ok": bool(_api_allowed(provider) and usage and usage["pct"] >= 99)})


async def _sc_model_back_once(now: float | None = None) -> list[str]:
    """Teammates moved to another model go back once that quota has reset (unless Lu changed it since)."""
    now = time.time() if now is None else now
    d, back = _model_fb_load(), []
    for name, r in list(d.items()):
        if now < float(r.get("until") or 0):
            continue
        d.pop(name, None)
        if name in (config or {}).get("agents", {}) and _current_model(name)[1] == r.get("to"):
            _sc_team.set_override(name, "model", r.get("from") or "", config)
            back.append(name)
    _model_fb_save(d)
    for name in back:
        await _sc_restart_quiet(name)
    return back


async def _sc_api_heal() -> list[str]:
    """Anyone on a backup key goes back to the plan when the switch is off or the plan has room
    again (11-11: pm sat on a key with no money for 1.5 hours; nothing brought it back)."""
    back = []
    for name, rec in list(_sc_keys.all_on_api().items()):
        provider = (rec or {}).get("provider") or ""
        usage = _sc_quota.provider_usage(provider, _current_model(name)[1])
        if not _api_allowed(provider) or (usage and usage["pct"] < 99):
            _sc_keys.end_api(name)
            back.append(name)
    for name in back:
        await _sc_restart_quiet(name)
    return back


async def _sc_api_back_loop():
    """Every 10 minutes: teammates that have been on the API for 5 hours go back to their plan.
    If the plan is still out, they hit the limit again and come straight back to the key."""
    await asyncio.sleep(20)
    try:
        await _sc_api_heal()   # on start too: a teammate left on a key by an older version comes back
    except Exception:
        _log_rate_limited("api heal failed")
    while True:
        await asyncio.sleep(300)
        try:
            await _sc_api_heal()
            for name in _sc_keys.due_back():
                _sc_keys.end_api(name)
                await _sc_restart_quiet(name)
            await _sc_model_back_once()
            await _sc_qa_tick()
        except Exception:
            _log_rate_limited("api fallback check failed")


@app.on_event("startup")
async def _sc_api_back_start():
    asyncio.create_task(_sc_api_back_loop())
    asyncio.create_task(_sc_due_loop())


_SC_QA: list = []


def _sc_qa():
    if not _SC_QA:
        data_dir = Path((config or {}).get("server", {}).get("data_dir", "./data"))
        _SC_QA.append(_sc_qask.State(data_dir / "quota_ask.json"))
    return _SC_QA[0]


async def _sc_qa_move_if_planned(base: str, provider: str, channel: str, after_api: bool = False) -> bool:
    """Lu's pick for this plan says: carry on on another app until the reset. True if moved."""
    st = _sc_qa()
    plan = st.approved.get(provider) or {}
    to = plan.get("then")
    if not to or time.time() >= float(plan.get("until") or 0) or base in st.moved:
        return False
    why = "备用 API key 用不了" if after_api else f"{_sc_qask.APP_NAMES.get(provider, provider)} 额度用完了"
    return await _sc_qa_move(base, to, float(plan["until"]), channel, why + "，按 Lu 的选择")


async def _sc_qa_move(base: str, to: str, until: float, channel: str, why: str) -> bool:
    """Run a teammate on another app until `until`, then _sc_qa_tick puts it back as it was."""
    st = _sc_qa()
    if base in st.moved or base not in (config or {}).get("agents", {}):
        return False
    provider = _current_model(base)[0]
    ov = (_sc_team.load_overrides().get(base) or {})
    cfg = (config or {}).get("agents", {}).get(base, {})
    st.moved[base] = {"provider": _sc_team.provider_of(cfg.get("command", "")) or provider,
                      "model": ov.get("model") or cfg.get("model") or "",
                      "effort": ov.get("effort") or cfg.get("effort") or "",
                      "until": float(until)}
    st.save()
    try:
        _sc_team.set_override(base, "provider", to, config)
        if _sc_qask.STANDIN_MODEL.get(to):
            _sc_team.set_override(base, "model", _sc_qask.STANDIN_MODEL[to], config)
    except ValueError:
        st.moved.pop(base, None); st.save()
        return False
    when = time.strftime("%m-%d %H:%M", time.localtime(float(until)))
    store.add(base, f"{why}，换到 {_sc_qask.APP_NAMES.get(to, to)} 接着干，{when} 换回来。", channel=channel)
    await broadcast_team_changed()
    asyncio.create_task(_sc_restart_quiet(base))
    return True


async def _sc_qa_tick(now: float | None = None) -> None:
    """Every 5 min: ask Lu once per plan window at 98%; put moved teammates back after the reset."""
    now = time.time() if now is None else now
    st = _sc_qa()
    changed = False
    # put back
    for base, rec in list(st.moved.items()):
        if now < float(rec.get("until") or 0):
            continue
        st.moved.pop(base, None); changed = True
        if base not in (config or {}).get("agents", {}):
            continue
        try:
            _sc_team.set_override(base, "provider", rec.get("provider") or "claude", config)
            if rec.get("model"):
                _sc_team.set_override(base, "model", rec["model"], config)
            if rec.get("effort"):
                _sc_team.set_override(base, "effort", rec["effort"], config)
        except ValueError:
            pass
        store.add(base, "额度重置了，换回原来的应用。", channel=_pm_channel())
        await broadcast_team_changed()
        asyncio.create_task(_sc_restart_quiet(base))
    for p, a in list(st.approved.items()):
        if now >= float(a.get("until") or 0):
            st.approved.pop(p, None); changed = True
    # ask
    groups: dict[str, dict] = {}
    for h, cfg in ((config or {}).get("agents", {}) or {}).items():
        prov, model = _current_model(h)
        u = _sc_quota.provider_usage(prov, model)
        if not u:
            continue
        # one question per plan window; without a reset time, one per day
        # One question per plan window. Agent Monitor's label flips language ("每周" / "Weekly") and its
        # reset time moves by an hour, so key on the provider (+ Cursor's pool) and compare resets loosely
        # (11-13: the same question went out 4 times in one night).
        pool = u["label"] if prov == "cursor" else ""
        key = f"{prov}:{pool}" + ("" if u.get("resets") else time.strftime(":%Y-%m-%d", time.localtime(now)))
        g = groups.setdefault(key, {"provider": prov, "pct": u["pct"], "resets": u.get("resets"), "who": []})
        g["who"].append(_label_of(h))
    for key, g in groups.items():
        prev = st.asked.get(key)
        same = (prev is not None and g["resets"] is not None and abs(float(prev) - float(g["resets"])) < 6 * 3600) \
            or (prev is not None and g["resets"] is None)
        if g["pct"] < _sc_qask.ASK_AT or same:
            continue
        other = _sc_qask.standin(g["provider"], _sc_quota.provider_usage)
        has_key = bool(_sc_keys.get_key(g["provider"])) if g["provider"] in ("claude", "codex") else False
        q = _sc_qask.question(g["provider"], g["pct"], g["resets"], g["who"], has_key, other,
                              owner=str(room_settings.get("username") or "Lu"), now=now)
        st.asked[key] = g["resets"]; changed = True
        if not q:
            continue
        text, choices = q
        store.add("Scranton", text, msg_type="decision", channel=_pm_channel(),
                  metadata={"choices": choices, "resolved": False,
                            "quota_ask": {"provider": g["provider"], "until": g["resets"] or (now + 5 * 3600),
                                          "then": other[0] if other else None}})
    if changed:
        st.save()


@app.post("/api/scranton/quota/move")
async def scranton_quota_move(request: Request):
    """Lu, 11-11 (A): move teammates off a plan that's running low until that plan resets.
    {"names": [...], "to": "codex", "from": "claude"}. They come back on their own at the reset."""
    body = await request.json()
    to, frm = str(body.get("to") or ""), str(body.get("from") or "claude")
    u = _sc_quota.provider_usage(frm, "")
    until = float((u or {}).get("resets") or 0)
    if to not in _sc_qask.APP_NAMES or not until:
        return JSONResponse({"ok": False, "error": "need a known app and a reset time for the plan"}, status_code=400)
    done = []
    for n in body.get("names") or []:
        if _current_model(str(n))[0] == frm and await _sc_qa_move(str(n), to, until, _pm_channel(),
                                                                  f"为了把 {_sc_qask.APP_NAMES.get(frm, frm)} 额度留给项目经理和 QA（Lu 定）"):
            done.append(n)
    return JSONResponse({"ok": True, "moved": done, "until": until})


def _sc_qa_apply(meta: dict, chosen: str) -> None:
    """Lu answered the 98% question: remember it for when the plan really runs out."""
    qa = (meta or {}).get("quota_ask") or {}
    p = qa.get("provider")
    if not p:
        return
    mode = _sc_qask.classify(chosen)
    st = _sc_qa()
    if mode in ("api", "move"):
        st.approved[p] = {"mode": mode, "until": float(qa.get("until") or 0), "then": qa.get("then")}
    else:
        st.approved.pop(p, None)
    st.save()


_SC_DUE: list = []


def _sc_due_book():
    if not _SC_DUE:
        data_dir = Path((config or {}).get("server", {}).get("data_dir", "./data"))
        _SC_DUE.append(_sc_due_mod.DueBook(data_dir / "due.json"))
    return _SC_DUE[0]


def _sc_due_text(handle: str, it: dict) -> str:
    when = time.strftime("%H:%M", time.localtime(float(it["due"])))
    ref = f" (#{it['id']})" if it.get("id") else ""
    return (f"@pm {_label_of(handle)} 的活{ref}说 {when} 交，现在过了还没交。"
            f"看一下它卡在哪，重新定时间或者换人；不用告诉 Lu，除非要她定。")


def _label_of(handle: str) -> str:
    try:
        return str(((config or {}).get("agents", {}).get(handle, {}) or {}).get("label") or handle)
    except Exception:
        return handle


_sc_idle_since: dict[str, float] = {}   # teammate -> when it last went quiet (heartbeat activity)
IDLE_POKE_MIN = 15


def _sc_idle_pokes(board, now: float) -> list[tuple[str, str, int | None, str]]:
    """Lu, 11-12: a row said 在做 while the teammate sat at its prompt (it said "转入定帧任务" and its
    turn ended; nobody woke it). Running, quiet for 15+ min, with a 在做 row: poke it once per 30 min.
    Returns (channel, handle, reply_to, text)."""
    import mcp_bridge
    out = []
    with board.lock:
        for ch, rows in board.data.items():
            for r in rows:
                h = str(r.get("who") or "")
                if r.get("state") != "doing" or h not in (config or {}).get("agents", {}):
                    continue
                names = [n for n in list(mcp_bridge._presence) if n.split("-")[0] == h]
                if not names or any(mcp_bridge._activity.get(n) for n in names):
                    continue
                if not any(now - mcp_bridge._presence.get(n, 0) < 90 for n in names):
                    continue   # not running: that's for the PM, not a poke
                quiet = min((_sc_idle_since.get(n, now) for n in names), default=now)
                if now - quiet < IDLE_POKE_MIN * 60 or now - float(r.get("poked") or 0) < 1800:
                    continue
                # At most twice per row until someone changes it (11-13: 40 pokes in one night, most to
                # people waiting on someone else, each one a paid wake-up).
                if float(r.get("poked") or 0) < float(r.get("at") or 0):
                    r["pokes"] = 0
                if int(r.get("pokes") or 0) >= 2:
                    continue
                r["poked"] = now
                r["pokes"] = int(r.get("pokes") or 0) + 1
                mins = int((now - quiet) // 60)
                out.append((ch, h, r.get("msg") if isinstance(r.get("msg"), int) else None,
                            f"@{h} Your asks 上「{str(r.get('ask', ''))[:50]}」还是在做，你已经停了 {mins} 分钟。"
                            f"接着做；做不了就一句话说卡在哪。"))
        if out:
            board._save()
    return out


async def _sc_board_tick() -> None:
    """Your asks: PR merged → row live; rows untouched for 4 h and people over 5 rows → one note to the PM."""
    import mcp_bridge, scranton_board
    if mcp_bridge.BOARD is None:
        return
    for ch, h, reply_to, text in _sc_idle_pokes(mcp_bridge.BOARD, time.time()):
        store.add("Scranton", text, channel=ch, reply_to=reply_to)
    reps = await asyncio.to_thread(scranton_board.housekeeping, mcp_bridge.BOARD, _pr_state)
    night = time.localtime().tm_hour >= 23 or time.localtime().tm_hour < 7
    for ch, rep in reps.items():
        # Night: no "update the board" notes. They wake the project manager, who runs on Claude
        # (11-12 night: 15 of them; Claude went 87 % → 98 % in a day). The rows stay marked stale.
        if night:
            continue
        if rep["stale"] or rep.get("overloaded"):
            text = scranton_board.nudge_text(rep, _label_of)
            if text:
                store.add("Scranton", text, channel=ch)


async def _sc_due_loop():
    """Once a minute: anyone past their '交 HH:MM' with nothing delivered → tell the PM once.
    Every 10 minutes: tidy the asks board (merged PRs, stale rows)."""
    await asyncio.sleep(30)
    tick = 0
    while True:
        tick += 1
        if tick % 10 == 1:
            try:
                await _sc_board_tick()
            except Exception:
                _log_rate_limited("board tick failed")
        try:
            for h, it in _sc_due_book().overdue():
                store.add("Scranton", _sc_due_text(h, it), channel=it.get("channel") or "general",
                          reply_to=it.get("id") if isinstance(it.get("id"), int) else None)
                await _broadcast_json({"type": "scranton_due", "items": _sc_due_book().public()})
        except Exception:
            _log_rate_limited("due check failed")
        await asyncio.sleep(60)


@app.get("/api/scranton/board")
async def scranton_board_get(channel: str = "general"):
    import mcp_bridge, scranton_board
    if mcp_bridge.BOARD is None:
        return JSONResponse({"rows": [], "summary": ""})
    rows = mcp_bridge.BOARD.rows(channel)
    return JSONResponse({"rows": rows, "summary": scranton_board.summary(rows) if rows else "",
                         "states": scranton_board.STATE_ZH})


@app.get("/api/scranton/due")
async def scranton_due_list():
    return JSONResponse(_sc_due_book().public())
