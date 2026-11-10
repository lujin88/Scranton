"""Token use for the Report: how many tokens the team used, which tasks used the most, and what to change.

Read from the apps' own session logs on this Mac (nothing is sent anywhere):
  - Claude Code: ~/.claude/projects/*/*.jsonl  (assistant messages carry `usage`)
  - Codex (ChatGPT): ~/.codex/sessions/**/rollout-*.jsonl  (`token_count` events)
  - Cursor keeps no such log: not counted, and the Report says so.

Which teammate a session belongs to: the `sender` it uses in its chat_send / chat_read calls
(every Scranton teammate posts as itself). Sessions that never talk to Scranton are left out.

Which task: each usage moment is put on the latest request to that teammate before it (a message
that @-ed it, or its DM), grouped by thread. That's an estimate and the Report says so.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

# "sender":"pm" in JSON, escaped once or twice (Codex custom tools wrap the call in code), or a
# code literal like sender: 'visual'.
_SENDER = re.compile(r'''(?:\\*"|\b)sender(?:\\*")?\s*[:=]\s*\\*["']([A-Za-z0-9_-]{1,40})''')
_cache: dict = {}
_lock = threading.Lock()   # the warm-up at start and a Report request must not read the same files at once


def _ts(v) -> float:
    if isinstance(v, (int, float)):
        return float(v) / (1000 if v > 1e12 else 1)
    try:
        return _dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _files(base: Path, pattern: str, since: float):
    if not base.is_dir():
        return []
    out = []
    for p in base.glob(pattern):
        try:
            if p.stat().st_mtime >= since:
                out.append(p)
        except OSError:
            pass
    return out


# Per-file parse cache: logs only grow, so each call reads just the new tail.
# path -> {"ino", "off", "senders": Counter, "rows": {key: row}}
_files_seen: dict = {}


def _scan(f: Path, parse_line, own_call):
    """Read f from where we stopped last time; return (senders, rows). Partial last lines wait."""
    try:
        st = f.stat()
    except OSError:
        return None
    c = _files_seen.get(str(f))
    if not c or c["ino"] != st.st_ino or st.st_size < c["off"]:
        c = {"ino": st.st_ino, "off": 0, "senders": Counter(), "rows": {}, "cwd": ""}
        _files_seen[str(f)] = c
    if st.st_size > c["off"]:
        try:
            with open(f, "rb") as fh:
                fh.seek(c["off"])
                chunk = fh.read()
        except OSError:
            return c["senders"], c["rows"], c["cwd"]
        cut = chunk.rfind(b"\n") + 1
        pos = c["off"]
        for raw in chunk[:cut].split(b"\n")[:-1]:
            line = raw.decode("utf-8", "replace")
            if not c["cwd"] and '"cwd"' in line:
                m = _CWD.search(line)
                if m:
                    c["cwd"] = m.group(1)
            if "sender" in line and own_call(line):
                c["senders"].update(_SENDER.findall(line))
            r = parse_line(line, pos)
            if r:
                c["rows"][r[0]] = r[1]
            pos += len(raw) + 1
        c["off"] += cut
        # an unterminated last line: count it if it's whole JSON, but read it again next time
        # (rows are keyed, so the re-read replaces it rather than adding)
        tail = chunk[cut:].decode("utf-8", "replace")
        if tail.strip():
            r = parse_line(tail, c["off"])
            if r:
                c["rows"][r[0]] = r[1]
    return c["senders"], c["rows"], c["cwd"]


# Which teammate a session is: the sender in ITS OWN tool calls. Tool results (chat_read output)
# are full of other people's senders; counting those gave nearly every session to pm (11-09).
def _claude_call(line):
    return '"type":"assistant"' in line or '"type": "assistant"' in line


def _codex_call(line):
    return ('"function_call"' in line or '"custom_tool_call"' in line or '"mcp_tool_call_begin"' in line) \
        and '_output"' not in line


_CWD = re.compile(r'"cwd"\s*:\s*"([^"]{1,400})"')
_WT = re.compile(r'-worktrees/([A-Za-z0-9_-]{1,40})/?$')
_GENERIC = {"codex", "claude", "user", "agent", "cursor", "assistant"}


def _who(senders: Counter, cwd: str):
    """The teammate a session belongs to. Its own git worktree says it best (<repo>-worktrees/<name>,
    made by scranton.sh). Otherwise the name it posts as, but not a generic one: Codex teammates
    often post as "codex" and the server fills in who they are."""
    m = _WT.search(cwd or "")
    if m:
        return m.group(1)
    for name, _n in senders.most_common():
        if name.lower() not in _GENERIC:
            return name
    return None


def _claude_line(line, pos):
    if '"usage"' not in line:
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    msg = d.get("message") or {}
    u = msg.get("usage") or {}
    if not u or d.get("type") != "assistant":
        return None
    # streamed chunks repeat the same usage: keep one per (message, request)
    return (msg.get("id"), d.get("requestId")), (
        _ts(d.get("timestamp")),
        int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0),
        int(u.get("cache_read_input_tokens") or 0),
        int(u.get("output_tokens") or 0))


def _codex_line(line, pos):
    if "token_count" not in line:
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    p = d.get("payload") or {}
    if p.get("type") != "token_count":
        return None
    u = ((p.get("info") or {}).get("last_token_usage")) or {}
    if not u:
        return None
    cached = int(u.get("cached_input_tokens") or 0)
    return pos, (_ts(d.get("timestamp")), max(0, int(u.get("input_tokens") or 0) - cached), cached,
                         int(u.get("output_tokens") or 0) + int(u.get("reasoning_output_tokens") or 0))


def _sessions(base: Path, pattern: str, since: float, parse_line, own_call, app: str):
    """Yield (agent_or_None, [(ts, fresh_in, cached_in, out)], app) per session file."""
    for f in _files(base, pattern, since):
        got = _scan(f, parse_line, own_call)
        if not got:
            continue
        senders, rows, cwd = got
        rows = [r for r in rows.values() if r[0] >= since]
        if rows:
            yield _who(senders, cwd), rows, app, f


def _claude_sessions(since: float, home: Path):
    return _sessions(home / ".claude" / "projects", "*/*.jsonl", since, _claude_line, _claude_call, "claude")


def _codex_sessions(since: float, home: Path):
    base = Path(os.environ.get("CODEX_HOME") or home / ".codex") / "sessions"
    return _sessions(base, "**/rollout-*.jsonl", since, _codex_line, _codex_call, "codex")


def build(msgs: list[dict], team: dict, owner: str, days: int, home: Path | None = None) -> dict:
    with _lock:
        return _build(msgs, team, owner, days, home)


def _build(msgs: list[dict], team: dict, owner: str, days: int, home: Path | None = None) -> dict:
    home = home or Path.home()
    since = time.time() - days * 86400
    key = (days, len(msgs), msgs[-1]["id"] if msgs else -1)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 120:
        return hit[1]

    handles = {h.lower() for h in team}
    base = lambda s: re.sub(r"-\d+$", "", str(s or "").lower())   # noqa: E731

    by_id = {m.get("id"): m for m in msgs}

    def root_of(m):
        cur, n = m, 0
        while cur and cur.get("reply_to") is not None and n < 50:
            nxt = by_id.get(cur["reply_to"])
            if not nxt:
                return cur["reply_to"]
            cur, n = nxt, n + 1
        return cur.get("id") if cur else None

    # requests to each teammate: who/what woke it, in time order
    triggers: dict = defaultdict(list)
    for m in msgs:
        t = float(m.get("timestamp") or 0)
        if t < since - 86400 or m.get("type", "chat") not in ("chat", "decision"):
            continue
        frm = base(m.get("sender"))
        text = str(m.get("text") or "")
        ch = str(m.get("channel") or "")
        hit_handles = {base(h) for h in re.findall(r"@([A-Za-z0-9_-]+)", text)} & handles
        if ch.startswith("dm-"):
            hit_handles.add(ch[3:])
        for h in hit_handles - {frm}:
            triggers[h].append((t, m))

    totals = Counter()
    per_agent: dict = defaultdict(Counter)
    per_task: dict = defaultdict(Counter)
    task_agents: dict = defaultdict(set)
    unassigned = 0
    apps = set()

    heavy = []                # (tokens, agent, app, path, first, last) per teammate session
    sessions = Counter()      # app -> session files with use in the period
    matched = Counter()       # app -> of those, ones tied to a teammate
    for gen in (_claude_sessions(since, home), _codex_sessions(since, home)):
        for agent, rows, app, path in gen:
            sessions[app] += 1
            agent = base(agent) if agent else None
            if not agent or agent not in handles:
                unassigned += sum(r[1] + r[2] + r[3] for r in rows)
                continue
            matched[app] += 1
            apps.add(app)
            heavy.append((sum(r[1] + r[2] + r[3] for r in rows), agent, app, path, min(r[0] for r in rows), max(r[0] for r in rows)))
            trig = triggers.get(agent, [])
            j = 0
            for t, fresh, cached, out in sorted(rows):
                c = Counter(fresh=fresh, cached=cached, out=out)
                totals.update(c)
                per_agent[agent].update(c)
                while j + 1 < len(trig) and trig[j + 1][0] <= t:
                    j += 1
                if trig and trig[j][0] <= t:
                    r = root_of(trig[j][1])
                    per_task[r].update(c)
                    task_agents[r].add(agent)

    tot = lambda c: c["fresh"] + c["cached"] + c["out"]   # noqa: E731
    all_tokens = tot(totals)

    agents = sorted(({"agent": a, "tokens": tot(c), "fresh": c["fresh"], "cached": c["cached"], "out": c["out"]}
                     for a, c in per_agent.items()), key=lambda x: -x["tokens"])
    tasks = []
    for r, c in sorted(per_task.items(), key=lambda kv: -tot(kv[1]))[:5]:
        m = by_id.get(r) or {}
        title = re.sub(r"\s+", " ", str(m.get("text") or "")).strip()
        tasks.append({"id": r, "channel": m.get("channel") or "general", "by": m.get("sender") or "",
                      "title": title[:140], "tokens": tot(c), "agents": sorted(task_agents[r])})

    tips = _tips(all_tokens, totals, agents, tasks, team, msgs, since)
    insight = _insight(sorted(heavy, key=lambda x: -x[0]), all_tokens, team)
    data = {
        "available": bool(all_tokens),
        "total": all_tokens, "fresh": totals["fresh"], "cached": totals["cached"], "out": totals["out"],
        "agents": agents, "tasks": tasks, "tips": tips,
        "not_counted": sorted({base(h) for h, a in team.items()
                               if str(a.get("command", "")) in ("agent", "cursor-agent")}),
        "unassigned": unassigned,
        "sessions": dict(sessions), "matched": dict(matched),
        "top_sessions": insight["sessions"], "top_actions": insight["actions"],
    }
    _cache.clear()
    _cache[key] = (time.time(), data)
    return data


def _pct(a, b):
    return round(100 * a / b) if b else 0


def _tips(all_tokens, totals, agents, tasks, team, msgs, since):
    """At most three, each from this period's numbers. Nothing is said without a number behind it."""
    tips = []
    if not all_tokens:
        return tips
    cache_share = _pct(totals["cached"], all_tokens)
    if cache_share >= 70 and agents:
        heavy = max(agents, key=lambda a: a["cached"])
        tips.append(f"{cache_share}% of all tokens are agents re-reading their earlier conversation. "
                    f"The most is {heavy['agent']}: give it a fresh session after each finished task "
                    f"(Settings → Fresh sessions) so it doesn't carry the whole day along.")
    if agents:
        top = agents[0]
        share = _pct(top["tokens"], all_tokens)
        model = str((team.get(top["agent"]) or {}).get("model") or "")
        cmd = str((team.get(top["agent"]) or {}).get("command") or "")
        if share >= 30 and cmd == "claude" and ("opus" in model.lower() or not model):
            tips.append(f"{top['agent']} used {share}% of the tokens on {'Opus' if model else 'the default model'}. "
                        "If most of its work is routine (status, lists, hand-offs), Sonnet is enough: "
                        "change it under its Model in Settings → Agents.")
        elif share >= 40:
            tips.append(f"{top['agent']} alone used {share}% of the tokens. Check whether it is being woken "
                        "for things another teammate already handles.")
    if tasks:
        t = tasks[0]
        share = _pct(t["tokens"], all_tokens)
        if share >= 15:
            n = len(t["agents"])
            tips.append(f"One thread took {share}% of the tokens with {n} teammate{'s' if n != 1 else ''} in it. "
                        + ("Many teammates in one thread each re-read all of it: split it, or let the project "
                           "manager pass on only what each one needs." if n >= 3 else
                           "If it went back and forth a lot, a clearer first request saves the most."))
    loops = sum(1 for m in msgs if float(m.get("timestamp") or 0) >= since
                and str(m.get("sender")).lower() == "system" and str(m.get("text", "")).startswith("Loop guard:"))
    if loops and len(tips) < 3:
        tips.append(f"The team was paused {loops} time{'s' if loops != 1 else ''} for handing work back and forth "
                    "without you. Each hand-off wakes another agent that re-reads the thread.")
    return tips[:3]


def codex_shape(home: Path | None = None, files: int = 5) -> dict:
    """Which kinds of Codex log lines mention a sender (kinds only, no content): to see why
    Codex sessions aren't tied to a teammate."""
    home = home or Path.home()
    base = Path(os.environ.get("CODEX_HOME") or home / ".codex") / "sessions"
    kinds: Counter = Counter()
    for f in sorted(_files(base, "**/rollout-*.jsonl", time.time() - 7 * 86400), key=lambda p: -p.stat().st_mtime)[:files]:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "sender" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        kinds["unparsed"] += 1
                        continue
                    p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
                    k = f'{d.get("type")}/{p.get("type")}/{"call" if _codex_call(line) else "-"}'
                    kinds[k] += 1
                    if _SENDER.search(line):
                        kinds[k + "/found"] += 1
                        if _codex_call(line):
                            for name in _SENDER.findall(line)[:3]:
                                kinds["name:" + name[:20]] += 1
        except OSError:
            pass
    return dict(kinds)



# ----------------------------------------------------------------------------------------------
# What the heaviest sessions keep re-reading, and the actions repeated most (Lu, 11-09: a total
# alone says nothing; show what's repeated and what to change).
#
# Each reply re-reads everything above it in the session. So a piece of context costs about
# (its size) x (replies after it). We add that up per kind of thing and per repeated action.
# Sizes are characters, so these are shares, not exact tokens.

_TOOL_KIND = {
    "chat_read": "Chat it read", "chat_resync": "Chat it read", "chat_send": "Its own posts",
    "read": "Files it opened", "grep": "File searches", "glob": "File searches",
    "bash": "Command output", "shell": "Command output", "exec_command": "Command output",
    "webfetch": "Web pages", "websearch": "Web pages", "task": "Sub-agents", "agent": "Sub-agents",
    "edit": "Its own edits", "write": "Its own edits", "multiedit": "Its own edits", "apply_patch": "Its own edits",
}
_analysis_cache: dict = {}


def _tool_name(n):
    n = str(n or "").split("__")[-1].split(".")[-1]
    return n


def _sig(name, args):
    """A short label for 'the same action': chat_read #lu-portfolio, Read bar.md, git status."""
    n = _tool_name(name)
    a = args if isinstance(args, dict) else {}
    if not a and isinstance(args, str):
        try:
            a = json.loads(args)
        except ValueError:
            a = {"cmd": args}
    low = n.lower()
    if low in ("chat_read", "chat_resync"):
        return f"chat_read #{a.get('channel') or 'all'}" + (" (whole thread)" if a.get("job_id") else "")
    if low in ("read", "edit", "write"):
        fp = str(a.get("file_path") or a.get("path") or "")
        return f"{n} {fp.rsplit('/', 1)[-1] or '?'}"
    if low in ("bash", "shell", "exec_command"):
        cmd = a.get("command") or a.get("cmd") or ""
        if isinstance(cmd, list):
            cmd = cmd[-1] if cmd else ""
        # "cd somewhere && git status": the command is the part after the cd
        parts = [p.strip() for p in re.split(r"&&|;|\|\|", str(cmd)) if p.strip()]
        cmd = next((p for p in parts if not re.match(r"^(cd|export|source|set)\b", p)), parts[0] if parts else "")
        words = [w for w in re.split(r"\s+", str(cmd).strip()) if w and not w.startswith("-") and "=" not in w]
        words = [w.rsplit("/", 1)[-1] for w in words]
        if words and words[0] in ("gh-push.sh", "test-lock.sh", "timeout", "sudo", "env"):
            words = words[1:]
        if words and words[0] in ("python", "python3", "node") and (len(words) < 2 or not re.match(r"^[\w./-]+\.(py|js|mjs)$", words[1])):
            return f"{words[0]} (inline script)"
        words = [w for w in words if re.match(r"^[\w./:@#-]+$", w)]
        return " ".join(words[:3])[:60] or f"{n} (other)"
    if low in ("webfetch",):
        u = str(a.get("url") or "")
        return "WebFetch " + (re.sub(r"^https?://", "", u).split("/")[0] or "?")
    return n


def _analyze(path: Path, app: str) -> dict:
    """Walk one session: what sits in its context and how many replies re-read it."""
    try:
        st = path.stat()
    except OSError:
        return {}
    ck = (str(path), st.st_size)
    if ck in _analysis_cache:
        return _analysis_cache[ck]
    items = []        # [kind, sig, size, calls_before]
    calls = 0
    seen_ids = set()
    pending = {}      # tool call id -> (name, args)
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if app == "claude":
                if d.get("type") == "system" and "compact" in str(d.get("subtype", "")):
                    items = []   # compacted: earlier context is gone
                    continue
                msg = d.get("message") or {}
                content = msg.get("content")
                if d.get("type") == "assistant":
                    mid = msg.get("id")
                    if mid and mid not in seen_ids and msg.get("usage"):
                        seen_ids.add(mid)
                        calls += 1
                    for c in content if isinstance(content, list) else []:
                        if c.get("type") == "tool_use":
                            pending[c.get("id")] = (c.get("name"), c.get("input") or {})
                            items.append(["Its own replies and thinking", "", len(json.dumps(c.get("input") or {})), calls])
                        elif c.get("type") in ("text", "thinking"):
                            items.append(["Its own replies and thinking", "", len(str(c.get("text") or c.get("thinking") or "")), calls])
                elif d.get("type") == "user":
                    if isinstance(content, str):
                        _prompt_items(items, content, calls)
                        continue
                    for c in content if isinstance(content, list) else []:
                        if c.get("type") == "tool_result":
                            name, args = pending.get(c.get("tool_use_id"), ("tool", {}))
                            body = c.get("content")
                            size, img = 0, 0
                            for part in body if isinstance(body, list) else [{"type": "text", "text": body}]:
                                if isinstance(part, dict) and part.get("type") == "image":
                                    img += 1600   # an image is about 1.6k tokens
                                else:
                                    size += len(str(part.get("text", "") if isinstance(part, dict) else part))
                            kind = _TOOL_KIND.get(_tool_name(name).lower(), "Other tools")
                            items.append([kind, _sig(name, args), size, calls])
                            if img:
                                items.append(["Screenshots and images", _sig(name, args), img * 3, calls])
                        elif c.get("type") == "text":
                            _prompt_items(items, str(c.get("text") or ""), calls)
                        elif c.get("type") == "image":
                            items.append(["Screenshots and images", "image you sent", 4800, calls])
            else:
                p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
                t = p.get("type")
                if d.get("type") == "compacted":
                    items = []
                    continue
                if t == "token_count" and (p.get("info") or {}).get("last_token_usage"):
                    calls += 1
                elif t == "message":
                    text = " ".join(str(x.get("text") or "") for x in p.get("content") or [] if isinstance(x, dict))
                    if p.get("role") == "user":
                        _prompt_items(items, text, calls)
                    elif p.get("role") == "assistant":
                        items.append(["Its own replies and thinking", "", len(text), calls])
                    else:
                        items.append(["Instructions at the start", "", len(text), calls])
                elif t in ("function_call", "custom_tool_call"):
                    args = p.get("arguments") if t == "function_call" else p.get("input")
                    pending[p.get("call_id")] = (p.get("name"), args)
                    items.append(["Its own replies and thinking", "", len(str(args or "")), calls])
                elif t in ("function_call_output", "custom_tool_call_output"):
                    name, args = pending.get(p.get("call_id"), ("tool", {}))
                    out = p.get("output")
                    size = len(out if isinstance(out, str) else json.dumps(out or ""))
                    items.append([_TOOL_KIND.get(_tool_name(name).lower(), "Other tools"), _sig(name, args), size, calls])
    kinds, acts = Counter(), defaultdict(lambda: [0, 0])
    for kind, sig, size, before in items:
        w = size * max(0, calls - before)
        kinds[kind] += w
        if sig:
            acts[sig][0] += 1
            acts[sig][1] += w
    res = {"calls": calls, "kinds": dict(kinds), "acts": {k: tuple(v) for k, v in acts.items()},
           "context": sum(i[2] for i in items)}
    _analysis_cache[ck] = res
    return res


def _prompt_items(items, text, calls):
    """A message Scranton typed in to wake the agent: the request itself, and the rules sent along."""
    i = text.find("\n\nTEAM: ") if "\n\nTEAM: " in text else text.find(" TEAM: ")
    if i >= 0:
        items.append(["Team rules sent with messages", "", len(text) - i, calls])
        text = text[:i]
    items.append(["Messages that woke it", "", len(text), calls])


_ADVICE = {
    "Chat it read": "It re-reads chat it already saw. Ask it to read only new messages (chat_read with since_id), "
                    "or have the project manager pass on just the lines it needs.",
    "Files it opened": "Big files stay in its memory and are re-read on every reply. Put what it always needs "
                       "in its role card, and have it read only the part it needs.",
    "Command output": "Long command output stays in its memory. Have it cut output down (| tail -40, --quiet).",
    "Screenshots and images": "Every screenshot is re-read on every later reply. Send fewer, smaller ones, "
                              "and start a fresh session after a visual check.",
    "Web pages": "Fetched web pages stay in its memory. Ask for a short summary instead of whole pages.",
    "Team rules sent with messages": "The team rules sent along with messages are a big share: Scranton can send them less often.",
    "Its own replies and thinking": "Its own long replies pile up. A fresh session after each finished task clears them.",
    "Messages that woke it": "Long requests and hand-offs pile up. Shorter hand-offs (what to do, link, done-when) help.",
    "Sub-agents": "Sub-agent reports stay in its memory. Ask sub-agents for a short result only.",
}


def _insight(heavy, all_tokens, team):
    """Top sessions (what each kept re-reading) and the actions repeated most across them."""
    sessions, acts = [], defaultdict(lambda: [0, 0, set()])
    shown = Counter()   # one card per teammate (Lu, 11-09: pm showed twice); count its other long sessions
    for tokens, agent, app, path, first, last in heavy[:8]:
        try:
            a = _analyze(path, app)
        except Exception:
            continue
        if not a or not a.get("kinds"):
            continue
        tw = sum(a["kinds"].values()) or 1
        for sig, (n, w) in a["acts"].items():
            acts[sig][0] += n
            acts[sig][1] += tokens * w / tw    # its share of this session's tokens
            acts[sig][2].add(agent)
        shown[agent] += 1
        if shown[agent] > 1:
            for x in sessions:
                if x["agent"] == agent:
                    x["more"] = shown[agent] - 1
            continue
        if len(sessions) < 3:
            mix = sorted(a["kinds"].items(), key=lambda kv: -kv[1])
            top = [{"what": k, "share": round(100 * v / tw)} for k, v in mix[:4] if v / tw >= 0.05]
            reps = sorted(((s, n, w) for s, (n, w) in a["acts"].items() if n >= 3), key=lambda x: -x[2])[:3]
            advice = []
            hours = (last - first) / 3600
            if a["calls"] >= 120 or hours >= 6:
                advice.append(f"One session for {a['calls']} replies over {hours:.0f} h. With Fresh sessions on "
                              f"(every 40 messages or 4 h) it would have started clean several times.")
            if mix and _ADVICE.get(mix[0][0]):
                advice.append(_ADVICE[mix[0][0]])
            sessions.append({"agent": agent, "tokens": tokens, "share": round(100 * tokens / all_tokens) if all_tokens else 0,
                             "replies": a["calls"], "hours": round(hours, 1), "mix": top,
                             "repeats": [{"what": s, "times": n, "share": round(100 * w / tw)} for s, n, w in reps],
                             "advice": advice[:2], "more": 0})
    top_acts = sorted(acts.items(), key=lambda kv: -kv[1][1])[:5]
    actions = []
    for sig, (n, tok, who) in top_acts:
        kind = next((v for k, v in _TOOL_KIND.items() if sig.lower().startswith(k)), None)
        if sig.startswith("chat_read"):
            kind = "Chat it read"
        elif sig.split(" ")[0] in ("Read",):
            kind = "Files it opened"
        elif kind is None:
            kind = "Command output"
        actions.append({"what": sig, "times": n, "tokens": int(tok), "agents": sorted(who),
                        "advice": _ACTION_ADVICE.get(kind, "")})
    return {"sessions": sessions, "actions": actions}


_ACTION_ADVICE = {
    "Chat it read": "Each read only brings what's new, but it stays in a long session and is re-sent with every reply after it. What helps: fewer wake-ups (@ only whoever must act now) and shorter sessions (Fresh sessions by size).",
    "Files it opened": "Opened again and again: put the part it needs into its role card, or read just that part.",
    "Command output": "Same command many times: keep the output short (| tail, --quiet), and don't re-run to check what didn't change.",
}


# ---------------------------------------------------------------- per day (Lu, 11-10)
# "选完了得让我看到改进": a day-by-day series, so the Report can show each change Lu picked with
# the numbers before and after it. Only teammates' sessions (same as the rest of the Report).
def daily(msgs: list[dict], team: dict, days: int = 14, home: Path | None = None) -> list[dict]:
    with _lock:
        home = home or Path.home()
        since = time.time() - days * 86400
        handles = {h.lower() for h in team}
        base = lambda s: re.sub(r"-\d+$", "", str(s or "").lower())   # noqa: E731
        day = lambda t: time.strftime("%Y-%m-%d", time.localtime(t))  # noqa: E731
        out: dict = defaultdict(lambda: {"calls": 0, "ctx": 0, "tokens": 0,
                                         "app": defaultdict(lambda: {"calls": 0, "ctx": 0, "tokens": 0}),
                                         "wakes": 0, "pm_wakes": 0})
        for gen in (_claude_sessions(since, home), _codex_sessions(since, home)):
            for agent, rows, app, _f in gen:
                if not agent or base(agent) not in handles:
                    continue
                for ts, fresh, cached, o in rows:
                    d = out[day(ts)]
                    for b in (d, d["app"][app]):
                        b["calls"] += 1
                        b["ctx"] += fresh + cached
                        b["tokens"] += fresh + cached + o
        for m in msgs:
            t = float(m.get("timestamp") or 0)
            if t < since or m.get("type", "chat") not in ("chat", "decision"):
                continue
            frm = base(m.get("sender"))
            hit = {base(h) for h in re.findall(r"@([A-Za-z0-9_-]+)", str(m.get("text") or ""))} & handles
            hit.discard(frm)
            if hit:
                out[day(t)]["wakes"] += len(hit)
                if frm == "pm":
                    out[day(t)]["pm_wakes"] += len(hit)
        res = []
        for k in sorted(out):
            d = out[k]
            res.append({"day": k, "calls": d["calls"], "tokens": d["tokens"], "wakes": d["wakes"], "pm_wakes": d["pm_wakes"],
                        "ctx_k": round(d["ctx"] / d["calls"] / 1000) if d["calls"] else None,
                        "apps": {a: {"calls": v["calls"], "tokens": v["tokens"],
                                     "ctx_k": round(v["ctx"] / v["calls"] / 1000) if v["calls"] else None}
                                 for a, v in d["app"].items()}})
        return res
