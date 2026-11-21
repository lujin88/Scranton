"""Which installed skills each teammate may see (Lu, 2026-11-21).

About fifty third-party skills were installed for every CLI on the Mac mini (~/.agents/skills).
Every teammate's session then carried all fifty descriptions, which costs quota and invites the
wrong skill. Each teammate gets an allow-list in config.toml ([team.skills.allow]); everything else
that is installed is switched off for that teammate when Scranton launches it:

- Claude Code: a settings file passed with --settings: skillOverrides "off" (hidden from the model
  and from the / menu) plus a Skill(name) deny rule as a second guard.
- Codex: -c skills.config=[{path=…, enabled=false}, …], nothing written to ~/.codex.
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
        f.write_text(json.dumps(claude_settings(allow, found, agent == str(s.get("updater") or "")), ensure_ascii=False, indent=1), "utf-8")
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
    use = ("Skills: use only " + ", ".join(allow) + "; ignore every other installed skill, even if you can see it."
           if allow else "Skills: you have none; ignore every installed skill, even if you can see it.")
    if agent == str(s.get("updater") or ""):
        upd = (f" Only you may run `npx skills update` (or add/remove), and only after {owner} approved your summary of what changes; "
               f"never let skills update on their own.")
    else:
        upd = " Never run `npx skills add`, `update` or `remove`."
    return use + upd
