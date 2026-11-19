"""MCP server for agent chat tools — runs alongside the web server.

Serves two transports for compatibility:
  - streamable-http on port 8200 (Claude Code, Codex, Qwen)
  - SSE on port 8201 (Gemini)
"""

import scranton_board
import re as _re_mod
import json
import os
import time
import logging
import threading
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

log = logging.getLogger(__name__)

# Shared state — set by run.py before starting
store = None
rules = None
summaries = None
jobs = None  # set by run.py — JobStore instance
room_settings = None  # set by run.py — dict with "channels" list etc.
registry = None       # set by run.py — RuntimeRegistry instance
config = None         # set by run.py — full config.toml dict
router = None         # set by run.py — Router instance
agents = None         # set by run.py — AgentManager instance
_presence: dict[str, float] = {}
_activity: dict[str, bool] = {}   # True = screen changed on last poll
_activity_ts: dict[str, float] = {}  # timestamp of last active=True heartbeat
ACTIVITY_TIMEOUT = 8  # auto-expire activity after 8s without a fresh active=True
_presence_lock = threading.Lock()   # guards both _presence and _activity
_renamed_from: set[str] = set()    # old names from renames — suppress leave messages
_cursors: dict[str, dict[str, int]] = {}  # agent_name → {channel_name → last_id}
_cursors_lock = threading.Lock()
_empty_read_count: dict[str, int] = {}  # sender → consecutive empty reads
# Last channel (or job_id) each agent explicitly read from. chat_send
# falls back to this when the caller omits the channel/job_id, so agents
# mentioned in #X don't accidentally reply in #general just because
# they forgot the channel param. Closes #58.
_last_read_channel: dict[str, str] = {}
_last_read_job_id: dict[str, int] = {}
_last_read_lock = threading.Lock()
PRESENCE_TIMEOUT = 10  # ~2 missed heartbeats (5s interval) = offline

# Roles — per-instance, persisted to roles.json
_roles: dict[str, str] = {}  # agent_name → role string
_ROLES_FILE: Path | None = None

# Cursor persistence — set by run.py to enable saving cursors across restarts
_CURSORS_FILE: Path | None = None

_MCP_INSTRUCTIONS = (
    "agentchattr — a shared chat channel for coordinating development between AI agents and humans. "
    "Use chat_send to post messages. Use chat_read to check recent messages. "
    "Use chat_join when you start a session to announce your presence. "
    "Use chat_rules to list or propose shared rules (humans approve via the web UI). "
    "Always use your own name as the sender — never impersonate other agents or humans.\n\n"
    "CRITICAL — Sender Identity Rules:\n"
    "Your BASE agent identity (used for chat_claim and chat_read) is:\n"
    "  - All Anthropic products (Claude Code, claude-cli, etc.) → base: \"claude\"\n"
    "  - All OpenAI products (Codex CLI, codex, chatgpt-cli, etc.) → base: \"codex\"\n"
    "  - All Google products (Gemini CLI, gemini-cli, aistudio, etc.) → base: \"gemini\"\n"
    "  - All Alibaba/Qwen products (Qwen Code, qwen-cli, etc.) → base: \"qwen\"\n"
    "  - All Kilo products (Kilo CLI, kilocode, etc.) → base: \"kilo\"\n"
    "  - Humans use their own name (e.g. \"user\")\n"
    "Do NOT use your CLI tool name (e.g. \"gemini-cli\", \"claude-code\") — use the base name above.\n"
    "IMPORTANT: When multiple instances run, the server renames slot 1 (e.g. \"claude\" → \"claude-1\"). "
    "If chat_send rejects your sender, call chat_claim(sender='your_base_name') and use the confirmed_name "
    "as your sender for ALL subsequent tool calls. The confirmed_name overrides the base name.\n\n"
    "CRITICAL — Identity:\n"
    "Always use your base agent name (claude/codex/gemini/qwen/kilo) as sender. "
    "Do NOT call chat_claim on fresh sessions — it is only for "
    "recovering a previous identity after /resume.\n\n"
    "CRITICAL — Always Respond In Chat:\n"
    "When you are addressed in a chat message (@yourname or @all agents), you MUST respond using chat_send "
    "in the same channel. NEVER respond only in your terminal/console output. The human and other agents "
    "cannot see your terminal — only chat messages are visible to everyone. If you need to do work first, "
    "do the work, then post your response/results in chat using chat_send.\n\n"
    "CRITICAL — Token-Aware Reading:\n"
    "Each chat_read call costs tokens. Default: one read per relevant channel per turn. "
    "A second read is fine if you can name the reason (checked a different channel, did work and expect a reply, "
    "recovering from an error). After an empty read ('No new messages'), do NOT read the same channel again — "
    "stop and wait for your next prompt. Never use chat_read as a sleep/wait loop.\n\n"
    "Rules are the shared working style for your agents. They are short imperative instructions that all agents should follow. "
    "At session start, call chat_rules(action='list') to read active rules — treat them as authoritative guidance. "
    "When you notice a repeated correction, a cross-agent convention, or a preference that should persist, "
    "propose it as a rule via chat_rules(action='propose'). Keep rules short and imperative (max 160 chars). "
    "Don't propose trivial or session-specific things. chat_decision is an alias for chat_rules (backward compat).\n\n"
    "Messages belong to channels (default: 'general'). Use the 'channel' parameter in chat_send and "
    "chat_read to target a specific channel. Omit channel or pass empty string to read from all channels.\n\n"
    "If you are addressed in chat, respond in chat — use chat_send to reply in the same channel. "
    "Do not take the answer back to your terminal session. "
    "If the latest message in a channel is addressed to you (or all agents), treat it as your active task "
    "and execute it directly. Reading a channel with no task addressed to you is just catching up — no action needed.\n\n"
    "Multi-instance support:\n"
    "When multiple instances of the same agent run simultaneously, each gets a unique identity.\n"
    "The server assigns names like claude-1, claude-2 automatically.\n"
    "On /resume, if your conversation history shows you previously used a different name (e.g. 'claude-music'), "
    "call chat_claim(sender='your_base_name', name='claude-music') to reclaim it.\n"
    "If chat_send rejects your sender with an identity error, call chat_claim first to get your identity.\n\n"
    "Summaries are per-channel snapshots that help agents catch up quickly. "
    "Use chat_summary(action='read') at session start to get context before reading raw messages. "
    "Use chat_summary(action='write', text='...') to update the summary ONLY when:\n"
    "- You are explicitly asked via /summary\n"
    "- The channel has had 20+ messages since the last summary\n"
    "Do NOT update the summary mid-conversation, after trivial exchanges, or when another agent just updated it. "
    "Do NOT summarize just because a task was discussed or abandoned — wait for the 20-message threshold or a human request. "
    "Keep summaries factual and concise (under 150 words) — focus on decisions made, tasks completed, and open questions.\n\n"
    "Jobs are bounded work conversations — like Slack threads with status tracking. "
    "When you are triggered with job_id=N, use chat_read(job_id=N) to read the job conversation. "
    "That read returns a header entry first, including the job title and body, followed by the thread messages. "
    "Then use chat_send(job_id=N, message='...') to reply within it. "
    "Job conversations are separate from the main timeline — your response should go to the job, not the channel.\n\n"
    "CRITICAL — Proposing Jobs:\n"
    "Agents must ONLY propose jobs using chat_propose_job when explicitly asked by the user, OR when the request is a clearly 'scoped task'. "
    "A task is scoped if it has: 1) Concrete outcome, 2) Specific boundary, 3) Clear done criteria, 4) Explicit owner/intention, and 5) Appropriate size. "
    "If these 5 checks do not pass, do NOT propose a job; instead, reply in chat to ask for clarification. "
    "This prevents over-use of the jobs feature for vague requests.\n\n"
    "To post a suggestion (Accept/Dismiss card) in a job, prefix your message with [suggestion]: "
    "chat_send(job_id=N, message='[suggestion] I recommend we refactor the auth module'). "
    "The human can Accept (triggers you with context) or Dismiss."
)

# --- Tool implementations (shared between both servers) ---


def _request_headers(ctx: Context | None):
    if ctx is None:
        return None
    try:
        request = ctx.request_context.request
    except Exception:
        return None
    return getattr(request, "headers", None)


def _extract_agent_token(ctx: Context | None) -> str:
    headers = _request_headers(ctx)
    if not headers:
        return ""
    auth = headers.get("authorization", "")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-agent-token", "").strip()


def _authenticated_instance(ctx: Context | None) -> dict | None:
    if not registry:
        return None
    token = _extract_agent_token(ctx)
    if not token:
        return None
    return registry.resolve_token(token)


def _resolve_tool_identity(
    raw_name: str,
    ctx: Context | None,
    *,
    field_name: str,
    required: bool = False,
) -> tuple[str, str | None]:
    provided = raw_name.strip() if raw_name else ""
    token = _extract_agent_token(ctx)
    inst = _authenticated_instance(ctx)
    if inst:
        resolved = inst["name"]
        # Scranton: a teammate that can see another teammate's connection (two Gemini teammates
        # share one MCP settings file) must not act through it under its own name.
        base = lambda n: _re_mod.sub(r"-\d+$", "", str(n or "").strip().lower())
        if provided and resolved and base(provided) != base(resolved):
            try:
                others = {base(n) for n in registry.get_all_names()}
            except Exception:
                others = set()
            if base(provided) in others:
                return "", (f"Error: this connection belongs to {resolved}, not {provided}. "
                            f"Use your own Scranton connection (scranton-{base(provided)}).")
        if resolved:
            _touch_presence(resolved)
        return resolved, None
    if token:
        return "", "Error: stale or unknown authenticated agent session. Re-register and retry."

    if not provided:
        if required:
            return "", f"Error: {field_name} is required."
        return "", None

    # Scranton: MCP is for agents only. Without a valid agent token nobody may act
    # under a name, so a local process can't post as Lu, "system" or "Scranton".
    return "", f"Error: authenticated agent session required for '{provided}'."


def _owner_name() -> str:
    try:
        import app
        return str(app.room_settings.get("username") or "Lu")
    except Exception:
        return "Lu"


def _address_owner(text: str) -> str:
    """A message that opens by speaking to Lu ("Lu，是我排慢了…", "Lu: 3 件事") is talking to her,
    so it gets the @ that puts it in her Activity (Lu, 11-10: they wrote "Lu" and she never saw it).
    "Lu 选了 A" (about her, no comma) stays plain. Who may @ her is still decided by
    [team] mentions_from: anyone else's @Lu goes to the project manager, as before."""
    t = str(text or "")
    names = {_owner_name(), "Lu"}
    alt = "|".join(_re_mod.escape(n) for n in sorted(names, key=len, reverse=True) if n)
    m = _re_mod.match(r"^(\s*)(" + alt + r")(?=\s*[，,:：、!！])", t)
    return f"{m.group(1)}@{t[len(m.group(1)):]}" if m else t


def chat_send(
    sender: str,
    message: str,
    choices: list[str] = [],
    image_path: str = "",
    reply_to: int = -1,
    channel: str = "",
    job_id: int = 0,
    ctx: Context | None = None,
) -> str:
    """Send a message to the agentchattr chat. Use your name as sender (claude/codex/user).
    Optionally attach a local image by providing image_path (absolute path). For several pictures
    (before and after, three options side by side) put one path per line, up to 6.
    Optionally reply to a message by providing reply_to (message ID).
    Channel/job_id resolution:
      - If you pass channel or job_id explicitly, that target is honored.
      - If you omit both, the message is routed to the last channel or
        job this sender read from via chat_read (so replying after
        `chat_read(channel="bugfixing")` lands in #bugfixing, not #general).
      - If this sender has never read anything, the message falls back to
        the 'general' channel.
    IMPORTANT: Always include the choices parameter. When asking a yes/no or
    multiple-choice question, provide the options so the user can respond with
    a single click:
      chat_send(sender="claude", message="Should I merge?", choices=["Yes", "No", "Show diff first"])
    If you recommend one option, put it first and end it with "（推荐）" (or "(recommended)").
    Mark nothing when you have no preference: the user reads an unmarked list as "no preference".
    Don't add an option that needs more words to act on (e.g. "Needs changes"): the card always
    ends with a "Something else" row where the user types their own answer or reason.
    Don't repeat the options in the message text; the card shows them.
    Never add an option that only reports back something you can check yourself (e.g. "Merged it"
    for a PR: check with `gh pr view <url> --json state` instead; Scranton marks merged PRs done).
    For normal messages without choices, pass choices=[]:
      chat_send(sender="claude", message="Done.", choices=[])"""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=True)
    if err:
        return err

    # Fallback routing: if caller omitted both channel and job_id, use
    # whatever target this sender last read from. Prevents agents that
    # forget the channel param from accidentally replying in #general.
    if sender and not channel and not job_id:
        with _last_read_lock:
            fallback_job = _last_read_job_id.get(sender, 0)
            fallback_channel = _last_read_channel.get(sender, "")
        woke = (getattr(agents, "woken", None) or {}).get(sender)
        if fallback_job:
            job_id = fallback_job
        elif woke and time.time() - woke[1] < WOKEN_FOR:
            channel = woke[0]            # answer where you were called
        elif fallback_channel:
            channel = fallback_channel
    # Final fallback if still nothing: original 'general' behavior.
    if not channel and not job_id:
        channel = "general"
    # Block pending instances (identity not yet confirmed)
    if registry and registry.is_pending(sender):
        return "Error: identity not confirmed. Call chat_claim(sender=your_base_name) to get your identity."
    # Block base family names when multi-instance is active
    # (but allow if sender is a registered+active instance — e.g. slot-1 'claude' that already claimed)
    if registry and sender in registry.get_bases() and registry.family_instance_count(sender) >= 2:
        inst = registry.get_instance(sender)
        if not inst or inst.get("state") != "active":
            return (f"Error: multiple {sender} instances are registered. "
                    f"Call chat_claim(sender='{sender}') to get your unique identity, then use the confirmed_name as sender.")
    # Block unregistered agent names (stale identity from resumed session)
    if registry and registry.is_agent_family(sender) and not registry.is_registered(sender):
        return f"Error: sender '{sender}' is not registered. Call chat_claim(sender=your_base_name) to get your identity."
    if not message.strip() and not image_path:
        return "Empty message, not sent."
    message = _address_owner(message)

    # Job-scoped send: post into a job conversation instead of main timeline
    if job_id and jobs:
        # Detect suggestion type from [suggestion] prefix
        text = message.strip()
        msg_type = "chat"
        if text.lower().startswith("[suggestion]"):
            msg_type = "suggestion"
            text = text[len("[suggestion]"):].strip()
        # Handle image attachment for job messages
        job_attachments = None
        if image_path:
            import shutil, uuid
            src = Path(image_path)
            if not src.exists():
                return f"Image not found: {image_path}"
            if src.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'):
                return f"Unsupported image type: {src.suffix}"
            raw_dir = "./uploads"
            if config and "images" in config:
                raw_dir = config["images"].get("upload_dir", raw_dir)
            upload_dir = Path(raw_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{uuid.uuid4().hex[:8]}{src.suffix}"
            shutil.copy2(str(src), str(upload_dir / filename))
            job_attachments = [{"name": src.name, "url": f"/uploads/{filename}"}]
        msg = jobs.add_message(job_id, sender, text, msg_type=msg_type,
                               attachments=job_attachments)
        if msg is None:
            return f"Error: job #{job_id} not found."
        with _presence_lock:
            _presence[sender] = time.time()

        # Route @mentions in job messages to trigger other agents
        if router and agents:
            job = jobs.get(job_id)
            if job:
                job_channel = job.get("channel", "general")
                raw_targets = router.get_targets(sender, text, job_channel)
                targets = []
                for t in raw_targets:
                    if registry:
                        targets.extend(registry.resolve_to_instances(t))
                    else:
                        targets.append(t)
                targets = list(dict.fromkeys(targets))
                chat_msg = f"{sender}: {text}" if text else ""
                for target in targets:
                    if registry:
                        inst = registry.get_instance(target)
                        if inst and inst.get("state") == "pending":
                            continue
                    if agents.is_available(target):
                        agents.trigger_sync(target, message=chat_msg,
                                            channel=job_channel, job_id=job_id)

        return f"Sent to job #{job_id} (msg_id={msg['id']})" + (
            " [suggestion]" if msg_type == "suggestion" else "")

    attachments = []
    if image_path:
        import shutil
        import uuid
        from pathlib import Path
        # Several pictures in one message (Lu, 11-18): one path per line. Up to 6, checked before
        # any is copied, so a wrong path sends nothing instead of half the set.
        paths = [p.strip() for p in str(image_path).splitlines() if p.strip()][:6]
        for one in paths:
            src = Path(os.path.expanduser(one))
            if not src.exists():
                return f"Image not found: {one}"
            if src.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'):
                return f"Unsupported image type: {src.suffix}"
        raw_dir = "./uploads"
        if config and "images" in config:
            raw_dir = config["images"].get("upload_dir", raw_dir)
        upload_dir = Path(raw_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        for one in paths:
            src = Path(os.path.expanduser(one))
            filename = f"{uuid.uuid4().hex[:8]}{src.suffix}"
            shutil.copy2(str(src), str(upload_dir / filename))
            attachments.append({"name": src.name, "url": f"/uploads/{filename}"})

    reply_id = reply_to if reply_to >= 0 else None
    if reply_id is not None and store.get_by_id(reply_id) is None:
        return f"Message #{reply_to} not found."
    message, why_not = _picture_check(sender, message, choices, image_path, channel)
    if why_not:
        return why_not
    moved = ""
    if reply_id is not None:
        # A reply belongs with the message it answers, whatever channel was passed.
        home = (store.get_by_id(reply_id) or {}).get("channel") or channel
        if home != channel:
            moved = f" Note: put in #{home}, where message #{reply_id} is (you passed #{channel})."
            channel = home
    else:
        owed = _owner_waiting(sender, channel, message)
        if owed:
            return (f"Not sent. {_owner_name()} wrote to you in #{owed[0]} at {owed[1]} and you haven't answered there. "
                    f"Answer in #{owed[0]} first (channel=\"{owed[0]}\"): her answer goes where she asked. "
                    f"If this is a different matter for #{channel}, send it after that, and say which project it is about.")

    # Determine message type and metadata based on choices
    msg_type = "chat"
    metadata = None
    clean_choices = [c for c in (choices if choices else []) if isinstance(c, str) and c.strip()]
    if clean_choices:
        msg_type = "decision"
        metadata = {"choices": clean_choices, "resolved": False}

    msg = store.add(sender, message.strip(), attachments=attachments,
                    reply_to=reply_id, channel=channel,
                    msg_type=msg_type, metadata=metadata)
    _update_cursor(sender, [msg], channel)
    with _presence_lock:
        _presence[sender] = time.time()
    return f"Sent (id={msg['id']})" + moved + _length_note(message, clean_choices) + _shown_hint(msg)


def _picture_check(sender: str, message: str, choices, image_path: str, channel: str):
    """Lu, 11-18: "PM 经常问我的问题我没办法回答，因为我要他配图，他也不给我配图". That day 12 of
    44 cards and 11 of 29 other questions to her came without a picture. A question to her has to
    show what it is about. Returns (message, error): the message loses its 「无图：…」 line."""
    owner = _owner_name()
    text = str(message or "")
    m = _re_mod.match(r"\s*无图[：:]\s*(\S[^\n]{3,})\n?", text)
    if m:
        return text[m.end():].lstrip() or text, ""          # said why there is nothing to show
    if not owner or str(image_path or "").strip() or sender.lower() in ("scranton", "system", owner.lower()):
        return text, ""
    to_owner = bool(_re_mod.search(r"@" + _re_mod.escape(owner) + r"(?![\w-])", text, _re_mod.I))
    has_choices = any(isinstance(c, str) and c.strip() for c in (choices or []))
    # A card, or a message that ends on a question. A "？" in the middle of a report doesn't count.
    last = next((l for l in reversed(text.strip().split("\n")) if l.strip()), "")
    asks = has_choices or bool(_re_mod.search(r"[?？]\s*$|吗[。 ]?$", last.strip()))
    if not (to_owner and asks):
        return text, ""
    return text, (
        f"Not sent. {owner} can't answer a question she can't see. Send it again with image_path = one picture "
        f"(absolute path) of what you are asking about: a screenshot of the page as it is now, or the options side by "
        f"side (A | B), or before | after. If you don't have one, make it first (ask whoever built it for a screenshot). "
        f"Only when there is truly nothing to look at (a login, an account, a schedule, a yes/no about process), "
        f"start the message with a line 「无图：why there is nothing to show」 and send again.")


WOKEN_FOR = 30 * 60      # a call counts as "where you were called" for half an hour
OWED_FOR = 15 * 60


def _owner_waiting(sender: str, channel: str, message: str):
    """Lu, 11-17: "我在 channel 1 里面讲，莫名其妙的回复会跑到 channel 2 里面去". A message that speaks to
    Lu is held back when she wrote to this teammate in another channel in the last 15 minutes and
    hasn't had an answer there. Returns (her channel, HH:MM) or None. Talking to teammates in other
    channels is never held back: only a message that @s her."""
    owner = _owner_name()
    if not owner or not _re_mod.search(r"@" + _re_mod.escape(owner) + r"(?![\w-])", message or "", _re_mod.I):
        return None
    base = _re_mod.sub(r"-\d+$", "", sender.lower())
    now = time.time()
    try:
        with store._lock:
            recent = list(store._messages[-600:])
    except Exception:
        return None
    asked = None
    for m in recent:
        ts = float(m.get("timestamp") or 0)
        if now - ts > OWED_FOR or m.get("type") not in ("chat", None):
            continue
        ch = m.get("channel") or "general"
        who = str(m.get("sender") or "")
        if who.lower() == owner.lower():
            to_me = ch == f"dm-{base}"[:20] or _re_mod.search(r"@" + _re_mod.escape(base) + r"(?![\w-])", str(m.get("text") or ""), _re_mod.I)
            body = _re_mod.sub(r"@[\w-]+", "", str(m.get("text") or "")).strip()
            # A click on a card ("A：…") or a bare "好"/"ok" is her answer, not a question waiting for one.
            if to_me and len(body) >= 4 and not _re_mod.match(r"^[A-Fa-f1-9]{1,2}\s*[：:]", body):
                asked = (ch, ts)
        elif asked and _re_mod.sub(r"-\d+$", "", who.lower()) == base and ch == asked[0] and ts > asked[1]:
            asked = None            # answered there
    if asked and asked[0] != channel:
        return asked[0], time.strftime("%H:%M", time.localtime(asked[1]))
    return None


LONG_MSG = 400   # Lu, 11-12: reports are at most three lines; webdev averaged 355 characters


def _length_note(message: str, choices: list) -> str:
    """Sent anyway; the sender is told so the next one is shorter. Questions with options are exempt."""
    text = (message or "").strip()
    if choices or len(text) <= LONG_MSG or _re_mod.search(r"(?m)^\s*[A-D][.、:：]\s", text):
        return ""
    return (f" Note: that was {len(text)} characters. Channel messages are at most 3 lines "
            "(result, link, what's missing); put details in the PR comment or a file and link it.")


def chat_propose_job(
    sender: str,
    title: str,
    body: str = "",
    channel: str = "general",
    ctx: Context | None = None,
) -> str:
    """Propose a job for human approval. Posts a proposal card in the timeline.
    The human can Accept (creates the job) or Dismiss. Agents must NOT create jobs
    directly — always propose and let the human decide.

    Args:
        title: Short job title (max 80 chars)
        body: Detailed description of the work (max 1000 chars)
        channel: Channel to post the proposal in
    """
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=True)
    if err:
        return err
    if not title.strip():
        return "Error: title is required."
    title = title.strip()[:80]
    body = (body or "").strip()[:1000]

    msg = store.add(
        sender, f"Job proposal: {title}",
        msg_type="job_proposal",
        channel=channel,
        metadata={"title": title, "body": body, "status": "pending"},
    )
    _update_cursor(sender, [msg], channel)
    with _presence_lock:
        _presence[sender] = time.time()
    return f"Proposed job (msg_id={msg['id']}): {title}"


def _resolve_attachments(attachments: list[dict]) -> list[dict]:
    """Add absolute file_path so local agents can read attached images or files."""
    if not attachments:
        return attachments
    raw_dir = "./uploads"
    if config and "images" in config:
        raw_dir = config["images"].get("upload_dir", raw_dir)
    upload_dir = Path(raw_dir).resolve()
    resolved = []
    for att in attachments:
        a = dict(att)
        url = a.get("url", "")
        if url.startswith("/uploads/"):
            filename = url.split("/")[-1]
            a["file_path"] = str(upload_dir / filename)
        resolved.append(a)
    return resolved


def _owner_words_for(m: dict) -> list[dict]:
    """Lu, 11-18: "我讲了好多遍，也画图了，但他还是没有参照着做". Her picture reached the project
    manager, who described it in words to whoever built it: of 144 assignments that day 3 carried
    a picture and 24 a file path, and the builder is woken with "read the channel", not with her
    message. So an assignment that cites her message (#17410) is handed over with her words and
    her pictures attached, whoever wrote the assignment."""
    if SAID is None or str(m.get("sender") or "").lower() == _owner_name().lower():
        return []
    import scranton_said as _S
    ids = _S.cited_ids(m.get("text"))
    out, seen = [], set()
    for i in ids:
        it = SAID.get(i)
        if not it or i in seen:
            continue
        seen.add(i)
        pics = [a.get("file_path") for a in _resolve_attachments([{"url": u} for u in it.get("atts") or []]) if a.get("file_path")]
        out.append({"id": i, "said": _S.body_of(it["text"])[:600], "pictures": pics,
                    **({"she_was_replying_to": it["ctx"]} if it.get("ctx") else {})})
        if len(out) >= 4:
            break
    return out


def _serialize_messages(msgs: list[dict]) -> str:
    """Serialize store messages into MCP chat_read output shape."""
    out = []
    for m in msgs:
        entry = {
            "id": m["id"],
            "sender": m["sender"],
            "text": m["text"],
            "type": m["type"],
            "time": m["time"],
            "channel": m.get("channel", "general"),
        }
        if m.get("attachments"):
            entry["attachments"] = _resolve_attachments(m["attachments"])
        said = _owner_words_for(m)
        if said:
            entry["owner_said"] = said
            entry["owner_said_note"] = ("Her own words and pictures for what this message cites. Open every picture "
                                        "(file_path) and look at it before you start. Where this message and her "
                                        "words or pictures differ, hers win; if you can't tell what she means, ask "
                                        "before building.")
        if m.get("reply_to") is not None:
            entry["reply_to"] = m["reply_to"]
        out.append(entry)
    # Her kept preferences for a project ride along with the last message read from its channel.
    if LESSONS is not None and out:
        last_of = {}
        for e in out:
            last_of[e["channel"]] = e
        for ch, e in last_of.items():
            text = LESSONS.text_for(ch)
            if text:
                e["project_lessons"] = text
    return json.dumps(out, ensure_ascii=False) if out else ""


def _load_cursors():
    """Load cursor state from disk (called by run.py after store init)."""
    global _cursors
    if _CURSORS_FILE is None or not _CURSORS_FILE.exists():
        return
    try:
        data = json.loads(_CURSORS_FILE.read_text("utf-8"))
        with _cursors_lock:
            _cursors.update(data)
    except Exception:
        log.warning("Failed to load cursor state from %s", _CURSORS_FILE)


def _save_cursors():
    """Persist cursor state to disk atomically (write temp + rename)."""
    if _CURSORS_FILE is None:
        return
    try:
        with _cursors_lock:
            snapshot = dict(_cursors)
        _CURSORS_FILE.parent.mkdir(parents=True, exist_ok=True)
        from safe_io import atomic_write
        atomic_write(_CURSORS_FILE, json.dumps(snapshot))
    except Exception:
        log.warning("Failed to save cursor state to %s", _CURSORS_FILE)


def _load_roles():
    """Load persisted roles from disk."""
    global _roles
    if _ROLES_FILE is None or not _ROLES_FILE.exists():
        return
    try:
        _roles = json.loads(_ROLES_FILE.read_text("utf-8"))
    except Exception:
        log.warning("Failed to load roles from %s", _ROLES_FILE)


def _save_roles():
    """Persist roles to disk atomically."""
    if _ROLES_FILE is None:
        return
    try:
        _ROLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        from safe_io import atomic_write
        atomic_write(_ROLES_FILE, json.dumps(_roles))
    except Exception:
        log.warning("Failed to save roles to %s", _ROLES_FILE)


def set_role(name: str, role: str):
    """Set or clear an agent's role. Empty string clears."""
    if role:
        _roles[name] = role
    else:
        _roles.pop(name, None)
    _save_roles()


def get_role(name: str) -> str:
    """Get an agent's current role, or empty string."""
    return _roles.get(name, "")


def get_all_roles() -> dict[str, str]:
    """All active roles."""
    return dict(_roles)


def migrate_identity(old_name: str, new_name: str):
    """Migrate all runtime state when an agent is renamed (presence, cursors, activity, roles)."""
    with _presence_lock:
        if old_name in _presence:
            _presence[new_name] = _presence.pop(old_name)
        if old_name in _activity:
            _activity[new_name] = _activity.pop(old_name)
        if old_name in _activity_ts:
            _activity_ts[new_name] = _activity_ts.pop(old_name)
        _renamed_from.add(old_name)  # suppress leave message for old name
    with _cursors_lock:
        if old_name in _cursors:
            _cursors[new_name] = _cursors.pop(old_name)
    with _last_read_lock:
        if old_name in _last_read_channel:
            _last_read_channel[new_name] = _last_read_channel.pop(old_name)
        if old_name in _last_read_job_id:
            _last_read_job_id[new_name] = _last_read_job_id.pop(old_name)
    if old_name in _roles:
        _roles[new_name] = _roles.pop(old_name)
        _save_roles()
    _save_cursors()


def purge_identity(name: str):
    """Remove all runtime state for a deregistered agent (presence, activity, cursors, roles)."""
    with _presence_lock:
        _presence.pop(name, None)
        _activity.pop(name, None)
        _activity_ts.pop(name, None)
    with _cursors_lock:
        _cursors.pop(name, None)
    with _last_read_lock:
        _last_read_channel.pop(name, None)
        _last_read_job_id.pop(name, None)
    if name in _roles:
        del _roles[name]
        _save_roles()
    _save_cursors()


def migrate_cursors_rename(old_name: str, new_name: str):
    """Move cursor and fallback entries from old channel to new channel."""
    with _cursors_lock:
        for agent_cursors in _cursors.values():
            if old_name in agent_cursors:
                agent_cursors[new_name] = agent_cursors.pop(old_name)
    with _last_read_lock:
        for sender, fallback in list(_last_read_channel.items()):
            if fallback == old_name:
                _last_read_channel[sender] = new_name
    _save_cursors()


def migrate_cursors_delete(channel: str):
    """Remove cursors and reset every stale fallback to #general."""
    with _cursors_lock:
        for agent_cursors in _cursors.values():
            agent_cursors.pop(channel, None)
    with _last_read_lock:
        for sender, fallback in list(_last_read_channel.items()):
            if fallback == channel:
                _last_read_channel[sender] = "general"
    _save_cursors()


def _update_cursor(sender: str, msgs: list[dict], channel: str | None):
    if sender and msgs:
        ch_key = channel if channel else "__all__"
        with _cursors_lock:
            agent_cursors = _cursors.setdefault(sender, {})
            agent_cursors[ch_key] = msgs[-1]["id"]
        _save_cursors()


def chat_read(
    sender: str = "",
    since_id: int = 0,
    limit: int = 20,
    channel: str = "",
    job_id: int = 0,
    ctx: Context | None = None,
) -> str:
    """Read chat messages. Returns JSON array with: id, sender, text, type, time, channel.

    Smart defaults:
    - First call with sender: returns last `limit` messages (full context).
    - Subsequent calls with same sender: returns only NEW messages since last read.
    - Pass since_id to override and read from a specific point.
    - Omit sender to always get the last `limit` messages (no cursor).
    - Pass channel to filter by channel name (default: all channels).
    - Pass job_id to read a specific job. Job reads return a header entry first,
      including title and body, followed by the thread messages."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=False)
    if err:
        return err

    # Job-scoped read: return job metadata plus the thread messages
    if job_id and jobs:
        job = jobs.get(job_id)
        msgs = jobs.get_messages(job_id)
        if job is None or msgs is None:
            return f"Error: job #{job_id} not found."
        # Remember so chat_send defaults back to this job thread.
        if sender:
            with _last_read_lock:
                _last_read_job_id[sender] = job_id
                _last_read_channel.pop(sender, None)
        title = (job.get("title") or "").strip()
        body = (job.get("body") or "").strip()
        header_text = f"Job: {title}" if title else f"Job #{job_id}"
        if body:
            header_text += f"\nDescription: {body}"
        out = [{
            "id": -1,
            "sender": "system",
            "text": header_text,
            "type": "job_header",
            "time": "",
            "job_id": job_id,
            "title": title,
            "body": body,
            "status": job.get("status", ""),
            "channel": job.get("channel", ""),
            "created_by": job.get("created_by", ""),
            "assignee": job.get("assignee", ""),
        }]
        for m in msgs:
            entry = {"id": m["id"], "sender": m["sender"], "text": m["text"],
                     "time": m.get("time", ""), "job_id": job_id}
            if m.get("attachments"):
                entry["attachments"] = _resolve_attachments(m["attachments"])
            if m.get("type"):
                entry["type"] = m["type"]
            if m.get("resolved"):
                entry["resolved"] = m["resolved"]
            out.append(entry)
        return json.dumps(out, ensure_ascii=False)

    ch = channel if channel else None
    # Remember the channel this agent just read so chat_send without an
    # explicit channel defaults here instead of falling back to "general".
    # Only record when a specific channel was requested — broad reads
    # (no channel) shouldn't overwrite a useful last-read.
    if sender and ch:
        with _last_read_lock:
            _last_read_channel[sender] = ch
            _last_read_job_id.pop(sender, None)
    if since_id:
        msgs = store.get_since(since_id, channel=ch)
    elif sender:
        ch_key = ch if ch else "__all__"
        with _cursors_lock:
            agent_cursors = _cursors.get(sender, {})
            cursor = agent_cursors.get(ch_key, 0)
        if cursor:
            msgs = store.get_since(cursor, channel=ch)
        else:
            msgs = store.get_recent(limit, channel=ch)
    else:
        msgs = store.get_recent(limit, channel=ch)

    msgs = msgs[-limit:]
    _update_cursor(sender, msgs, ch)
    serialized = _serialize_messages(msgs)

    # Escalating empty-read hints to discourage polling loops
    if not serialized and sender:
        _empty_read_count[sender] = _empty_read_count.get(sender, 0) + 1
        n = _empty_read_count[sender]
        if n == 1:
            serialized = "No new messages. Do not poll — wait for your next prompt."
        elif n == 2:
            serialized = ("No new messages. You have read with no results twice — "
                          "stop polling and wait for a trigger.")
        else:
            serialized = ("No new messages. STOP. Repeated empty reads waste tokens. "
                          "Wait for your next prompt.")
    elif sender:
        _empty_read_count[sender] = 0

    # Prepend identity breadcrumb if multi-instance
    if sender and registry and registry.is_registered(sender):
        multi = registry.family_instance_count(sender) >= 2
        if multi:
            inst = registry.get_instance(sender)
            if inst:
                breadcrumb = f"[identity: {inst['name']} | label: {inst['label']}]"
                serialized = f"{breadcrumb}\n{serialized}"
    return serialized


def chat_resync(
    sender: str,
    limit: int = 50,
    channel: str = "",
    ctx: Context | None = None,
) -> str:
    """Explicit full-context fetch.

    Returns the latest `limit` messages and resets the sender cursor
    to the latest returned message id.
    Pass channel to filter by channel name (default: all channels).
    """
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=True)
    if err:
        return err
    ch = channel if channel else None
    msgs = store.get_recent(limit, channel=ch)
    _update_cursor(sender, msgs, ch)
    serialized = _serialize_messages(msgs)
    return serialized


def chat_join(name: str, channel: str = "general", ctx: Context | None = None) -> str:
    """Announce that you've connected to agentchattr."""
    name, err = _resolve_tool_identity(name, ctx, field_name="name", required=True)
    if err:
        return err
    # Block pending instances (identity not yet confirmed)
    if registry and registry.is_pending(name):
        return "Error: identity not confirmed. Call chat_claim(sender=your_base_name) to get your identity."
    # Block base family names when multi-instance is active
    # (but allow if name is a registered+active instance — e.g. slot-1 'claude' that already claimed)
    if registry and name in registry.get_bases() and registry.family_instance_count(name) >= 2:
        inst = registry.get_instance(name)
        if not inst or inst.get("state") != "active":
            return (f"Error: multiple {name} instances registered. "
                    f"Call chat_claim(sender='{name}') to get your unique identity first.")
    # Block unregistered agent names (stale identity from resumed session)
    if registry and registry.is_agent_family(name) and not registry.is_registered(name):
        return f"Error: '{name}' is not registered. Call chat_claim(sender=your_base_name) to get your identity."
    store.add(name, f"{name} is online", msg_type="join", channel="general")
    online = _get_online()
    return f"Joined. Online: {', '.join(online)}"


def chat_who() -> str:
    """Check who's currently online in agentchattr."""
    online = _get_online()
    return f"Online: {', '.join(online)}" if online else "Nobody online."


def _touch_presence(name: str):
    """Update presence timestamp — called on any MCP tool use."""
    with _presence_lock:
        _presence[name] = time.time()


def _get_online() -> list[str]:
    now = time.time()
    with _presence_lock:
        return [name for name, ts in _presence.items()
                if now - ts < PRESENCE_TIMEOUT]


def is_online(name: str) -> bool:
    now = time.time()
    with _presence_lock:
        return name in _presence and now - _presence.get(name, 0) < PRESENCE_TIMEOUT


def set_active(name: str, active: bool):
    with _presence_lock:
        _activity[name] = active
        if active:
            _activity_ts[name] = __import__("time").time()


def is_active(name: str) -> bool:
    import time as _time
    with _presence_lock:
        if not _activity.get(name, False):
            return False
        # Auto-expire stale activity
        ts = _activity_ts.get(name, 0)
        if _time.time() - ts > ACTIVITY_TIMEOUT:
            _activity[name] = False
            return False
        return True


def chat_rules(
    action: str,
    sender: str,
    rule: str = "",
    reason: str = "",
    channel: str = "general",
    ctx: Context | None = None,
) -> str:
    """Manage shared rules — the working style for your agents. Agents can list and propose; humans approve via the web UI.

    Actions:
      - list: Returns active rules (the current working style).
      - propose: Propose a new rule for human approval. Requires rule text + sender + channel.

    Pass channel to place the proposal card in the correct chat channel (default: 'general').
    Agents cannot activate, edit, or delete rules — only humans can do that from the web UI."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=False)
    if err:
        return err
    action = action.strip().lower()

    if action == "list":
        active = rules.active_list()
        if not active["rules"]:
            return "No active rules."
        lines = [f"Active rules (epoch {active['epoch']}):"]
        for i, r in enumerate(active["rules"], 1):
            lines.append(f"  {i}. {r}")
        return "\n".join(lines)

    if action == "propose":
        if not rule.strip():
            return "Error: rule text is required."
        if not sender.strip():
            return "Error: sender is required."
        result = rules.propose(rule, sender, reason)
        # Add proposal card to chat timeline
        if store:
            store.add(
                sender, f"Rule proposal: {result['text']}",
                msg_type="rule_proposal",
                channel=channel or "general",
                metadata={"rule_id": result["id"], "text": result["text"], "status": "pending"},
            )
        return f"Proposed rule #{result['id']}: '{result['text']}'. Human will review in the Rules panel."

    if action in ("activate", "edit", "delete"):
        return f"Error: '{action}' is only available to humans via the web UI."

    return f"Unknown action: {action}. Valid actions: list, propose."


def chat_decision(
    action: str,
    sender: str,
    decision: str = "",
    reason: str = "",
    ctx: Context | None = None,
) -> str:
    """Backward-compatible alias for chat_rules. Use chat_rules instead."""
    return chat_rules(action=action, sender=sender, rule=decision, reason=reason, ctx=ctx)


# --- Server instances ---

def chat_set_hat(sender: str, svg: str, target: str = "", ctx: Context | None = None) -> str:
    """Set your avatar hat. Pass an SVG string (viewBox "0 0 32 16", max 5KB).
    The hat will appear above your avatar in chat. To remove, users can drag it to the trash.
    Color context for design — chat bg is dark (#0f0f17), avatar colors: claude=#da7756 (coral), codex=#10a37f (green), gemini=#4285f4 (blue), qwen=#8b5cf6 (violet).
    Optional: pass target to set a hat on another agent (e.g. target="qwen")."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=True)
    if err:
        return err
    hat_owner = target.strip() if target.strip() else sender
    import app
    err = app.set_agent_hat(hat_owner, svg)
    if err:
        return f"Error: {err}"
    if hat_owner != sender:
        return f"Hat set for {hat_owner} (by {sender})!"
    return f"Hat set for {sender}!"


def chat_claim(sender: str, name: str = "", ctx: Context | None = None) -> str:
    """Claim your identity in a multi-instance setup.

    - Without name: accept the auto-assigned identity and unlock chat_send.
    - With name: reclaim a previous identity (e.g. from a breadcrumb after /resume).

    Your sender must be your current registered name (the one assigned at registration).
    The identity breadcrumb in chat_read responses shows your current identity."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=True)
    if err:
        return err
    if not registry:
        return "Error: registry not available."
    target = name.strip() if name.strip() else None
    result = registry.claim(sender, target)
    if isinstance(result, str):
        return f"Error: {result}"
    # Touch presence with the CONFIRMED name (may differ from sender)
    confirmed = result.get("name", sender)
    _touch_presence(confirmed)
    return json.dumps({"confirmed_name": confirmed, "label": result.get("label", ""), "base": result.get("base", "")})


def chat_channels() -> str:
    """List all available channels. Returns a JSON array of channel names."""
    channels = room_settings.get("channels", ["general"]) if room_settings else ["general"]
    return json.dumps(channels)


def chat_summary(
    action: str,
    sender: str,
    text: str = "",
    channel: str = "",
    ctx: Context | None = None,
) -> str:
    """Read or write per-channel summaries. Summaries help agents catch up quickly.

    Actions:
      - read: Get the current summary for a channel (default: sender's last active channel).
      - write: Update the channel summary. Requires text (max 1000 chars).

    Keep summaries factual and concise (under 150 words). Focus on decisions made,
    tasks completed, and open questions."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=False)
    if err:
        return err
    action = action.strip().lower()
    channel = (channel or "general").strip()

    if action == "read":
        entry = summaries.get(channel)
        if not entry:
            return json.dumps({"channel": channel, "text": None, "message": f"No summary for #{channel} yet — one hasn't been written."})
        return json.dumps(entry, ensure_ascii=False)

    if action == "write":
        if not text.strip():
            return "Error: text is required."
        if len(text.strip()) > 1000:
            return "Error: summary too long (max 1000 characters)."
        # Get the latest message ID for staleness tracking
        latest_id = 0
        if store:
            recent = store.get_recent(1, channel=channel)
            if recent:
                latest_id = recent[-1]["id"]
        result = summaries.write(channel, text, sender, message_id=latest_id)
        if result is None:
            return "Error: failed to write summary."
        # Post a visual summary message to the timeline
        if store:
            store.add(sender, text.strip(), msg_type="summary", channel=channel)
        return f"Summary for #{channel} updated ({len(text.strip())} chars)."

    return f"Unknown action: {action}. Valid actions: read, write."


_HANDOFF_DIR = None   # set by run.py: <data>/handoffs
HANDOFF_MAX = 6000


def chat_handoff(sender: str, note: str, ctx: Context | None = None) -> str:
    """Save your handoff note before Scranton starts you a fresh session (only when Scranton
    asks for it). Write what the next you needs, as plain operational state, not a diary:
    what you're working on, decisions made and why, open items and who is waiting on what,
    the next step, and files / branches / PRs. Under ~40 lines. Overwrites your previous note."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=True)
    if err:
        return err
    text = str(note or "").strip()
    if not text:
        return "Error: the note is empty."
    if _HANDOFF_DIR is None:
        return "Error: handoffs aren't set up on this server."
    import re as _re
    base = _re.sub(r"-\d+$", "", sender.lower())
    if not _re.fullmatch(r"[a-z0-9_-]{1,40}", base):
        return "Error: bad name."
    from safe_io import atomic_write
    _HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(_HANDOFF_DIR / f"{base}.md", text[:HANDOFF_MAX])
    return f"Handoff saved ({min(len(text), HANDOFF_MAX)} chars). Scranton will start your fresh session with it."


BOARD = None   # set by run.py: scranton_board.Board(<data>/board.json)


def chat_board(sender: str, action: str = "read", channel: str = "", id: int = 0, ask: str = "",
               state: str = "", who: str = "", due: str = "", link: str = "", note: str = "",
               msg: int = 0, check: str = "", ctx: Context | None = None) -> str:
    """The pinned list of what the owner asked for in a channel, one row each, kept up to date by
    the project manager instead of status messages.

    action: read | set | remove.
      set without id adds a row (ask = what was asked, a few words). set with id changes that row:
      state (todo, doing, in_pr, waiting_qa, waiting_lu, live, blocked, later = put aside on purpose or waiting for other work), who (teammate handle),
      due ("10:30"), link (PR or page URL), note (one short line: what it's waiting on),
      check (how anyone can tell this row is right: 2 to 4 things a checker can LOOK AT, one per line,
      e.g. "390 宽不横向滚动" / "标题和参考图同字号同位置" / "点 Start 进到第 2 步"; not "好看" or "符合要求".
      Write it when you assign the row; if you cannot write one, the task is not clear yet: ask the owner),
      msg (the chat message id to open: for waiting_lu, the id of your question to the owner, from
      chat_send's "Sent (id=…)"; the owner clicks the row and lands there).
    When something moves (PR opened, QA passed, merged, live), change the row; don't post a message
    saying so unless someone has to act."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=False)
    if err:
        return err
    if BOARD is None:
        return "Error: the board isn't available."
    channel = (channel or _last_channel_of(sender) or "general").strip()
    action = (action or "read").strip().lower()
    try:
        if action == "read":
            return json.dumps({"channel": channel, "rows": BOARD.rows(channel)}, ensure_ascii=False)
        if action == "set":
            if (state or "").strip().lower() == "blocked" and scranton_board.PARKED_RE.search(note or ""):
                return ("Error: 卡住 (blocked) means someone has to act now and the row names who and what. This note says the work "
                        "was put aside or waits for other work: set state later (以后做) instead, with the reason in the note.")
            if (state or "").strip().lower().replace(" ", "_") == "waiting_lu" and not asked_owner(msg):
                return ("Error: 等你 (waiting_lu) means the owner has a question or finished work in front of her right now. "
                        "Send it to her first (chat_send, with the picture), then set the row with msg = that message's id. "
                        "If you will ask her later (\"08:00 问\"), the row is not 等你 yet: keep it doing or todo and put the time in due.")
            row = BOARD.upsert(channel, sender, id=id, ask=ask, state=state, who=who, due=due, link=link, note=note, msg=msg, check=check)
            out = {"ok": True, "row": row}
            if not row.get("check") and row.get("who") and row.get("state") in ("todo", "doing"):
                out["hint"] = ("This row has no check. Add check = 2 to 4 things a checker can look at to tell it is right "
                               "(one per line). Whoever does it and whoever checks it both read them.")
            return json.dumps(out, ensure_ascii=False)
        if action == "remove":
            return json.dumps({"ok": BOARD.remove(channel, id)})
    except ValueError as e:
        return f"Error: {e}"
    return "Error: action must be read, set or remove."


# Words that say the work is still under way: a message with these and no question is a progress report.
STILL_GOING_RE = _re_mod.compile(r"接着做|继续做|还在做|正在做|进行中|做完后|之后再|\d{1,2}[:：]\d{2}\s*(?:前)?交|交\s*\d{1,2}[:：]\d{2}|稍后|还剩|下一步")


def asked_owner(msg_id) -> bool:
    """Is this message something put to the owner: sent by a teammate and addressed to her (a
    question, a card, finished work)? A row may say 等你 only when it points at one."""
    try:
        m = store.get_by_id(int(msg_id or 0)) if store is not None else None
    except (TypeError, ValueError):
        m = None
    if not m:
        return False
    owner = _owner_name()
    if str(m.get("sender", "")).lower() in (owner.lower(), "lu"):
        return False
    if m.get("type") == "decision":
        return True
    text = str(m.get("text") or "")
    # "…motion 接着做，15:00 交" with a picture is progress, not something for her to answer
    # (Lu, 11-19: "这个为什么没有 option 呢？" on a row that asked nothing).
    if STILL_GOING_RE.search(text) and not _re_mod.search(r"[?？]|吗[。 ]?$|请.{0,6}(选|定|看|确认)|你(选|定|看|觉得)", text):
        return False
    return bool(_re_mod.search(r"(^|[^\w])@(" + _re_mod.escape(owner) + r"|lu)(?![\w-])", text, _re_mod.I))


def board_view(channel: str) -> list[dict]:
    """The board as Lu sees it, in the channel overview and in Activity alike (Lu, 11-18: rows said
    等你 for "08:00 问 Lu", a question nobody had sent yet). A 等你 row that points at no question
    to her is shown as 在做 with not_asked set; the stored row is left as the project manager wrote it."""
    rows = BOARD.rows(channel) if BOARD is not None else []
    for r in rows:
        if r.get("state") == "waiting_lu" and not asked_owner(r.get("msg")):
            r["state"], r["not_asked"] = "doing", True
        elif scranton_board.is_parked(r):
            r["state"], r["parked"] = "later", True     # 卡住 in name only: put aside, or waiting for other work
        elif (r.get("state") == "doing" and str(r.get("who") or "").lower() in (_owner_name().lower(), "lu")
              and not str(r.get("note") or "").startswith("Lu 回了")):
            r["yours"] = True                             # the owner said she would do this one herself
    return rows


SAID = None   # set by run.py: scranton_said.Said


def _shown_hint(msg: dict) -> str:
    """A picture sent with none of her message numbers never reaches her "Done, to check" list, so
    the work stays unjudged (11-19). Say so in the tool result, where the sender reads it, with
    the instructions still waiting in that channel. Nothing is posted to the chat."""
    import scranton_said as _S
    if SAID is None or not msg.get("attachments") or msg.get("type") == "decision" or isinstance(msg.get("reply_to"), int):
        return ""
    if _S.cited_ids(msg.get("text") or ""):
        return ""
    waiting = SAID.pending_for(msg.get("channel") or "general")[-6:]
    if not waiting:
        return ""
    lines = "; ".join(f"#{it['id']}「{_S.body_of(it['text'])[:40]}」" for it in waiting)
    return (f"\nThis has a picture but names none of the owner's messages, so she is not asked to check it. Still waiting for a result "
            f"in this channel: {lines}. If this picture is the result for any of them, call "
            f"chat_said(action=\"shown\", ids=[…], msg={msg['id']}). If it is for none, do nothing.")


def chat_said(sender: str, action: str = "open", channel: str = "", q: str = "", ids: list[int] | None = None,
              note: str = "", msg: int = 0, ctx: Context | None = None) -> str:
    """What the owner said in a channel, word for word, kept by Scranton (her words, her pictures,
    the message she was replying to). Use it instead of your memory.

    action:
      find  — everything she said in this channel about `q` (a page name, a slide number, a word
              she uses), oldest first: the last line is her latest word. Call it BEFORE you assign
              or change a page, and paste her lines and picture paths into the assignment.
      open  — what she said here that nobody has taken yet.
      skip  — these `ids` won't be done; `note` says why (she can see it).
      shown — your message `msg` (it carries the picture) is the result for these `ids`; she then
              checks it against her own words. Only needed when that message did not cite them.
    You take one by putting its number (#15247) in the message where you assign or do it, or by
    replying to it. There is no "take" call."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=False)
    if err:
        return err
    if SAID is None:
        return "Error: not available."
    import scranton_said as _S
    channel = (channel or _last_channel_of(sender) or "general").strip()
    action = (action or "open").strip().lower()
    if action == "find":
        if not str(q or "").strip():
            return "Error: find needs q (a page name, a slide number, a word she uses)."
        return json.dumps({"channel": channel, "q": q, "said": [_S.line(it) for it in SAID.find(channel, q)]}, ensure_ascii=False)
    if action == "open":
        return json.dumps({"channel": channel, "open": [_S.line(it) for it in SAID.open_items(channel)][-40:]}, ensure_ascii=False)
    if action == "skip":
        if not ids or not str(note or "").strip():
            return "Error: skip needs ids and a note saying why."
        return json.dumps({"skipped": SAID.skip(ids, sender, note)})
    if action == "shown":
        m = store.get_by_id(int(msg or 0)) if msg else None
        if not ids or not m or not m.get("attachments") or m.get("sender") != sender:
            return "Error: shown needs ids (her message numbers) and msg = the id of YOUR message that carries the picture."
        return json.dumps({"to_check": SAID.mark_done(ids, m["id"], sender)})
    return "Error: action must be find, open, skip or shown."


TEAM_MOVE = None   # set by run.py: app.sc_lead_move


def chat_team(sender: str, action: str = "runs_on", who: str = "", app: str = "", said: int = 0, ctx: Context | None = None) -> str:
    """Project manager only, and only to carry out what the owner said.

    action runs_on: run teammate `who` on another app (claude, chatgpt, cursor, gemini) because the
    owner said so, e.g. "Cursor 用完了，用 Claude 做". `said` = the id of HER message that names the app.
    The teammate restarts on that app and goes back by itself later. Do not pass this on to anyone
    else and do not ask her to do it in Settings: call this."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=False)
    if err:
        return err
    if (action or "").strip().lower() != "runs_on" or TEAM_MOVE is None:
        return "Error: action must be runs_on."
    return TEAM_MOVE(sender, who, app, said)


LESSONS = None   # set by run.py: scranton_lessons.Lessons


def chat_lessons(sender: str, action: str = "list", channel: str = "", lessons: str = "", ctx: Context | None = None) -> str:
    """The owner's preferences for a project: short lines distilled from what she keeps correcting.

    action:
      list    — the preferences she has kept for this channel's project, and the ones waiting for her.
      propose — `lessons`: one preference per line (at most 3, each one sentence a builder can follow,
                not about one page or one occasion). They reach the team only after she keeps them.
    Kept preferences arrive by themselves with chat_read (project_lessons); you do not pass them on."""
    sender, err = _resolve_tool_identity(sender, ctx, field_name="sender", required=False)
    if err:
        return err
    if LESSONS is None:
        return "Error: not available."
    channel = (channel or _last_channel_of(sender) or "general").strip()
    action = (action or "list").strip().lower()
    if action == "list":
        return json.dumps({"channel": channel, **LESSONS.get(channel)}, ensure_ascii=False)
    if action == "propose":
        lines = [l for l in str(lessons or "").splitlines() if l.strip()][:3]
        if not lines:
            return "Error: propose needs lessons, one per line."
        # each line has to point at her own messages in this channel: that is what she judges it by
        owner = _owner_name().lower()
        good, bad = [], []
        for line in lines:
            ids = [int(x) for x in _re_mod.findall(r"#(\d{3,7})", line)]
            hers = [i for i in ids if (m := (store.get_by_id(i) if store is not None else None))
                    and str(m.get("sender", "")).lower() in (owner, "lu") and (m.get("channel") or "general") == channel]
            (good if hers else bad).append(line)
        added = LESSONS.propose(channel, good, by=sender)
        if bad and not added:
            return ("Error: nothing proposed. Every line must end with the numbers of the owner's own messages in this channel "
                    "that it comes from, e.g. 「每页标题位置一致（#18127 #18136）」. She decides by reading her words next to the rule.")
        return json.dumps({"channel": channel, "proposed": [a["text"] for a in added],
                           "left_out": [b[:60] for b in bad],
                           "note": "Waiting for the owner to keep or drop each one. Do not announce them in the channel."}, ensure_ascii=False)
    return "Error: action must be list or propose."


def _last_channel_of(sender: str) -> str:
    with _last_read_lock:
        return str(_last_read_channel.get(sender) or "")


_ALL_TOOLS = [
    chat_send, chat_read, chat_resync, chat_join, chat_who, chat_rules, chat_decision,
    chat_channels, chat_set_hat, chat_claim, chat_summary, chat_propose_job, chat_handoff, chat_board, chat_said, chat_lessons, chat_team,
]


def _create_server(port: int) -> FastMCP:
    server = FastMCP(
        "agentchattr",
        host="127.0.0.1",
        port=port,
        log_level="ERROR",
        instructions=_MCP_INSTRUCTIONS,
    )
    for func in _ALL_TOOLS:
        # Scranton: plain text results only. With the default, FastMCP also sends
        # structuredContent {"result": "<the same text>"}; Claude Code shows that one, so chat_read's
        # JSON arrived escaped twice (a backslash showed as two, quotes as \") and agents "fixed"
        # commands that were right (Scranton issue, 2026-11-09).
        server.tool(structured_output=False)(func)
    return server


mcp_http = _create_server(8200)  # streamable-http for Claude/Codex/Qwen
mcp_sse = _create_server(8201)   # SSE for Gemini

# Keep backward compat — run.py references mcp_bridge.store
# (store is set by run.py before starting)


def run_http_server():
    """Block — run streamable-http MCP in a background thread."""
    mcp_http.run(transport="streamable-http")


def run_sse_server():
    """Block — run SSE MCP in a background thread."""
    mcp_sse.run(transport="sse")

