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
import time
from collections import Counter, defaultdict
from pathlib import Path

_SENDER = re.compile(r'\\?"sender\\?"\s*:\s*\\?"([A-Za-z0-9_-]{1,40})')
_cache: dict = {}


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


def _scan(f: Path, parse_line):
    """Read f from where we stopped last time; return (senders, rows). Partial last lines wait."""
    try:
        st = f.stat()
    except OSError:
        return None
    c = _files_seen.get(str(f))
    if not c or c["ino"] != st.st_ino or st.st_size < c["off"]:
        c = {"ino": st.st_ino, "off": 0, "senders": Counter(), "rows": {}}
        _files_seen[str(f)] = c
    if st.st_size > c["off"]:
        try:
            with open(f, "rb") as fh:
                fh.seek(c["off"])
                chunk = fh.read()
        except OSError:
            return c["senders"], c["rows"]
        cut = chunk.rfind(b"\n") + 1
        pos = c["off"]
        for raw in chunk[:cut].split(b"\n")[:-1]:
            line = raw.decode("utf-8", "replace")
            if "sender" in line:
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
    return c["senders"], c["rows"]


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


def _sessions(base: Path, pattern: str, since: float, parse_line, app: str):
    """Yield (agent_or_None, [(ts, fresh_in, cached_in, out)], app) per session file."""
    for f in _files(base, pattern, since):
        got = _scan(f, parse_line)
        if not got:
            continue
        senders, rows = got
        rows = [r for r in rows.values() if r[0] >= since]
        if rows:
            yield (senders.most_common(1)[0][0] if senders else None), rows, app


def _claude_sessions(since: float, home: Path):
    return _sessions(home / ".claude" / "projects", "*/*.jsonl", since, _claude_line, "claude")


def _codex_sessions(since: float, home: Path):
    base = Path(os.environ.get("CODEX_HOME") or home / ".codex") / "sessions"
    return _sessions(base, "**/rollout-*.jsonl", since, _codex_line, "codex")


def build(msgs: list[dict], team: dict, owner: str, days: int, home: Path | None = None) -> dict:
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

    for gen in (_claude_sessions(since, home), _codex_sessions(since, home)):
        for agent, rows, app in gen:
            agent = base(agent) if agent else None
            if not agent or agent not in handles:
                unassigned += sum(r[1] + r[2] + r[3] for r in rows)
                continue
            apps.add(app)
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
    data = {
        "available": bool(all_tokens),
        "total": all_tokens, "fresh": totals["fresh"], "cached": totals["cached"], "out": totals["out"],
        "agents": agents, "tasks": tasks, "tips": tips,
        "not_counted": sorted({base(h) for h, a in team.items()
                               if str(a.get("command", "")) in ("agent", "cursor-agent")}),
        "unassigned": unassigned,
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
