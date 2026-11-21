"""Which installed skills each teammate may see (Lu, 2026-11-21).

About fifty third-party skills were installed for every CLI on the Mac mini (~/.agents/skills).
Every teammate's session then carried all fifty descriptions, which costs quota and invites the
wrong skill. Each teammate gets an allow-list in config.toml ([team.skills.allow]); everything else
that is installed is switched off for that teammate when Scranton launches it:

- Claude Code: a settings file passed with --settings: skillOverrides "off" (hidden from the model
  and from the / menu) plus a Skill(name) deny rule as a second guard.
- Codex: -c skills.config=[{path=…, enabled=false}, …], nothing written to ~/.codex.
- Plugins (Claude Code only): enabledPlugins false in the same settings file for every plugin the
  teammate is not given in [team.skills.plugins]. Codex ignores per-session plugin switches.
- Cursor, Gemini and others have no per-session switch: for them only the sentence in the brief.

Allow-list semantics: a skill installed later is off for the team until someone lists it.
Lu's own sessions are not launched by Scranton and are not touched.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_DIRS = ("~/.agents/skills", "~/.claude/skills", "~/.codex/skills")
_NAME_RE = re.compile(r"(?m)^name:\s*[\"']?([A-Za-z0-9][\w.:-]{0,80})[\"']?\s*$")
# Installing, updating or removing skills changes what every session loads: one teammate only.
UPDATE_DENY = [f"Bash(npx skills {verb}{tail})" for verb in ("update", "add", "remove", "upgrade") for tail in (":*", " *", "")] + \
              ["Bash(npx -y skills:*)", "Bash(npx skills@latest:*)", "Bash(bunx skills:*)", "Bash(pnpm dlx skills:*)"]


def settings(cfg: dict) -> dict:
    s = ((cfg or {}).get("team") or {}).get("skills") or {}
    return s if isinstance(s, dict) else {}


def allowed(cfg: dict, agent: str) -> list[str] | None:
    """The teammate's allow-list, or None when skills are not limited at all."""
    s = settings(cfg)
    if not s.get("limit"):
        return None
    got = (s.get("allow") or {}).get(agent) or []
    return [str(x).strip() for x in (got if isinstance(got, list) else [got]) if str(x).strip()]


def installed(dirs=None) -> dict[str, list[str]]:
    """name -> SKILL.md paths, for every skill folder found (a skill linked into several places
    appears once per place, because each CLI is switched off by the path it reads)."""
    out: dict[str, list[str]] = {}
    for d in (dirs or DEFAULT_DIRS):
        root = Path(os.path.expanduser(str(d)))
        try:
            subs = sorted(p for p in root.iterdir() if p.is_dir() or p.is_symlink())
        except OSError:
            continue
        for sub in subs:
            f = sub / "SKILL.md"
            try:
                head = f.read_text("utf-8", errors="ignore")[:1500]
            except OSError:
                continue
            m = _NAME_RE.search(head[3:].split("\n---", 1)[0] if head.startswith("---") else head)
            for name in {sub.name, m.group(1) if m else sub.name}:
                out.setdefault(name, [])
                if str(f) not in out[name]:
                    out[name].append(str(f))
    return out


def off_for(allow: list[str], found: dict[str, list[str]]) -> dict[str, list[str]]:
    keep = {a.lower() for a in allow}
    kept_paths = {p for n, ps in found.items() if n.lower() in keep for p in ps}
    return {n: [p for p in ps if p not in kept_paths] for n, ps in found.items()
            if n.lower() not in keep and any(p not in kept_paths for p in ps)}


def claude_settings(allow: list[str], found: dict[str, list[str]], may_update: bool) -> dict:
    off = sorted(off_for(allow, found))
    deny = [f"Skill({n})" for n in off] + ([] if may_update else UPDATE_DENY)
    return {"skillOverrides": {n: "off" for n in off}, "permissions": {"deny": deny}}


def claude_plugins(home: str = "~/.claude") -> list[str]:
    """Ids ("name@marketplace") of the Claude Code plugins on this Mac: installed ones plus any
    the user's settings mention."""
    ids: set[str] = set()
    root = Path(os.path.expanduser(home))
    for f, key in ((root / "plugins" / "installed_plugins.json", "plugins"), (root / "settings.json", "enabledPlugins")):
        try:
            got = json.loads(f.read_text("utf-8")).get(key) or {}
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(got, dict):
            ids.update(str(k) for k in got)
    return sorted(i for i in ids if i.strip())


def plugins_off(cfg: dict, agent: str, ids: list[str]) -> dict[str, bool]:
    """Plugins bring their own skills, which skillOverrides does not reach. A teammate keeps only
    the plugins [team.skills.plugins] gives it; with no such table plugins are left alone."""
    table = settings(cfg).get("plugins")
    if not isinstance(table, dict):
        return {}
    keep = {str(x).strip().lower() for x in (table.get(agent) or [])}
    return {i: False for i in ids if i.split("@", 1)[0].lower() not in keep and i.lower() not in keep}


def codex_args(allow: list[str], found: dict[str, list[str]]) -> list[str]:
    paths = sorted({p for ps in off_for(allow, found).values() for p in ps})
    if not paths:
        return []
    return ["-c", "skills.config=[" + ",".join("{path=" + json.dumps(p) + ",enabled=false}" for p in paths) + "]"]


def launch_args(cfg: dict, agent: str, provider: str, data_dir: Path) -> list[str]:
    allow = allowed(cfg, agent)
    if allow is None:
        return []
    s = settings(cfg)
    found = installed(s.get("dirs") or None)
    if provider == "claude":
        d = Path(data_dir) / "provider-config"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{agent}-skills.json"
        body = claude_settings(allow, found, agent == str(s.get("updater") or ""))
        off = plugins_off(cfg, agent, claude_plugins())
        if off:
            body["enabledPlugins"] = off
        f.write_text(json.dumps(body, ensure_ascii=False, indent=1), "utf-8")
        return ["--settings", str(f)]
    if provider == "codex":
        return codex_args(allow, found)
    return []


def brief_line(cfg: dict, agent: str) -> str:
    allow = allowed(cfg, agent)
    if allow is None:
        return ""
    s = settings(cfg)
    owner = str(((cfg or {}).get("team") or {}).get("owner") or "the owner")
    use = ("Skills: yours are " + ", ".join(allow) + ". At the start of each task check whether one fits and use it without being asked; "
           "name the skill you used in your hand-in. Ignore every other installed skill, even if you can see it."
           if allow else "Skills: you have none; ignore every installed skill, even if you can see it.")
    if agent == str(s.get("updater") or ""):
        upd = (f" Only you may run `npx skills update` (or add/remove), and only after {owner} approved your summary of what changes; "
               f"never let skills update on their own.")
    else:
        upd = " Never run `npx skills add`, `update` or `remove`."
    return use + upd


_DESC_RE = re.compile(r"(?ms)^description:\s*(?:[>|][+-]?\s*\n)?(.*?)(?=^\w[\w-]*:\s|\Z)")
_about_cache: dict = {"at": 0.0, "v": {}}


def about(dirs=None, ttl: float = 300.0) -> dict[str, str]:
    """name -> one line saying what the skill is for (its own description), so Lu can pick one
    without remembering fifty names."""
    import time
    key = tuple(dirs or ())
    if time.time() - _about_cache["at"] < ttl and _about_cache["v"] and _about_cache.get("key") == key:
        return _about_cache["v"]
    out: dict[str, str] = {}
    for name, paths in installed(dirs).items():
        try:
            head = Path(paths[0]).read_text("utf-8", errors="ignore")[:3000]
        except OSError:
            continue
        fm = head[3:].split("\n---", 1)[0] if head.startswith("---") else ""
        m = _DESC_RE.search(fm)
        text = " ".join((m.group(1) if m else "").strip().strip("\"'").split())
        out[name] = text[:200]
    _about_cache.update(at=time.time(), v=out, key=key)
    return out


def for_team(cfg: dict) -> dict[str, list[dict]]:
    """teammate -> [{name, about}] for the composer."""
    s = settings(cfg)
    if not s.get("limit"):
        return {}
    info = about(s.get("dirs") or None)
    found = {k.lower() for k in info}
    return {a: [{"name": n, "about": info.get(n, ""), "installed": n.lower() in found} for n in allowed(cfg, a) or []]
            for a in (s.get("allow") or {})}
