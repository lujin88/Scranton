#!/usr/bin/env python3
"""Runs when a Claude teammate is about to finish a turn (a Claude Code Stop hook).

Lu, 11-24: hand-ins arrive unchecked and the same thing is said many times. Rules in a role card
are text a teammate may skip; this is run by the machine. When the teammate's branch changed since
the last pass, two checks run on what it changed:

  1. types: `tsc --noEmit`, only errors in files the branch touched
  2. sizes: a font size that this part of the project has never used (and is not a size token)

A failure exits 2 with the findings on stderr: Claude Code hands them back and the teammate keeps
working. Never a trap: the same change is sent back at most twice, a run Claude Code already
continued from is let through, and anything this script cannot judge passes.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BLOCKS = 2
TSC_SECONDS = 150
TOKEN_FILES = ("design-system/tokens.css", "design-system/tokens.json", "design-system-foundation.css",
               "app/globals.css", "src/styles/tokens.css", "styles/tokens.css")
_SIZE_RE = re.compile(r"font-?size\s*:\s*['\"]?(\d+(?:\.\d+)?)(px|rem)\b", re.I)
_TOKEN_RE = re.compile(r"(--[\w-]*font-size[\w-]*|--fs-[\w-]+|--text-[\w-]+)\s*:\s*([^;]+);")


def _git(cwd: Path, *args: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(["git", "--no-optional-locks", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def base_of(cwd: Path) -> str:
    """Where this branch left the default branch: everything after it is the teammate's change."""
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        b = _git(cwd, "merge-base", "HEAD", ref).strip()
        if b:
            return b
    return "HEAD"


def to_px(num: str, unit: str) -> float:
    return float(num) * (16.0 if unit.lower() == "rem" else 1.0)


def tokens(cwd: Path) -> dict[str, float]:
    """name -> px for the project's font-size tokens with a plain value (clamp() ones have no single size)."""
    out: dict[str, float] = {}
    for rel in TOKEN_FILES:
        f = cwd / rel
        try:
            text = f.read_text("utf-8", "replace")
        except OSError:
            continue
        for name, val in _TOKEN_RE.findall(text):
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)(px|rem)\s*", val)
            if m:
                out.setdefault(name, to_px(m.group(1), m.group(2)))
    return out


def in_use(cwd: Path, base: str, top: str) -> dict[float, int]:
    """Font sizes this part of the project already uses (px -> how often), as of the base."""
    out: dict[float, int] = {}
    spec = [top] if top else ["."]
    text = _git(cwd, "grep", "-h", "-o", "-I", "-E", r"font-?size[[:space:]]*:[[:space:]]*['\"]?[0-9.]+(px|rem)", base, "--", *spec, timeout=30)
    for num, unit in _SIZE_RE.findall(text):
        px = round(to_px(num, unit), 2)
        out[px] = out.get(px, 0) + 1
    return out


def size_findings(cwd: Path, base: str, diff: str, toks: dict[str, float]) -> list[str]:
    """A font size nobody used before in that part of the project. Lu, 11-22 on a deck: "越改越乱…
    不存在 89 这样子". Sizes already in use there, or on the token scale, pass: forcing 14px to the
    nearest token would change pages she did not ask to change."""
    out, path, line, cache = [], "", 0, {}
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else ""
            continue
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", raw)
        if m:
            line = int(m.group(1)) - 1
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            line += 1
            if not re.search(r"\.(css|scss|tsx|jsx|vue|html)$", path) or any(path.endswith(t) for t in TOKEN_FILES):
                continue
            if "ds-ok" in raw:
                continue
            for num, unit in _SIZE_RE.findall(raw):
                px = round(to_px(num, unit), 2)
                top = path.split("/", 1)[0] if "/" in path else ""
                if top not in cache:
                    used = {k for k, n in in_use(cwd, base, top).items() if n >= 2}
                    cache[top] = used | {round(v, 2) for v in toks.values()}
                known = cache[top]
                if len(known) < 3 or any(abs(px - k) < 0.05 for k in known):
                    continue
                near = sorted(known, key=lambda k: abs(k - px))[:3]
                out.append(f"{path}:{line}  font-size {num}{unit} is new: nothing in {top or 'this project'}/ uses it. "
                           f"Sizes in use near it: {', '.join(f'{k:g}px' for k in sorted(near))}. Use one of those, "
                           f"or keep it and say why on that line: /* ds-ok: reason */")
        elif raw.startswith(" "):
            line += 1
    return out[:12]


def type_findings(cwd: Path, changed: list[str]) -> list[str]:
    tsc = cwd / "node_modules" / ".bin" / "tsc"
    files = [c for c in changed if re.search(r"\.(ts|tsx)$", c)]
    if not files or not tsc.exists() or not (cwd / "tsconfig.json").exists():
        return []
    try:
        r = subprocess.run([str(tsc), "--noEmit", "-p", "."], cwd=cwd, capture_output=True, text=True, timeout=TSC_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return []                                  # too slow or not runnable here: not this check's call
    if r.returncode == 0:
        return []
    mine = [ln for ln in (r.stdout + r.stderr).splitlines() if any(ln.startswith(f + "(") or ln.startswith(f + ":") for f in files)]
    return mine[:12]


def _state(agent: str) -> Path:
    d = ROOT / "data" / "stop-check"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{re.sub(r'[^A-Za-z0-9_-]', '', agent) or 'agent'}.json"


def _log(agent: str, cwd: Path, result: str, n: int) -> None:
    try:
        with (ROOT / "data" / "stop-check" / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "agent": agent, "repo": cwd.name, "result": result, "findings": n}) + "\n")
    except OSError:
        pass


def run(agent: str, payload: dict) -> tuple[int, str]:
    if payload.get("stop_hook_active"):
        return 0, ""                               # already sent back once in this stop: let it finish
    cwd = Path(str(payload.get("cwd") or ".")).expanduser()
    top = _git(cwd, "rev-parse", "--show-toplevel").strip()
    if not top:
        return 0, ""
    cwd = Path(top)
    base = base_of(cwd)
    diff = _git(cwd, "diff", "--unified=0", base, "--", ".", timeout=30)
    if not diff.strip():
        return 0, ""
    key = hashlib.sha1(diff.encode("utf-8", "replace")).hexdigest()
    sf = _state(agent)
    try:
        st = json.loads(sf.read_text("utf-8"))
    except (OSError, ValueError):
        st = {}
    mine = st.get(str(cwd)) or {}
    if mine.get("passed") == key:
        return 0, ""
    blocks = int(mine.get("blocks", 0)) if mine.get("key") == key else 0
    changed = [ln for ln in _git(cwd, "diff", "--name-only", base, "--", ".").splitlines() if ln.strip()]
    found = type_findings(cwd, changed) + size_findings(cwd, base, diff, tokens(cwd))
    if not found:
        st[str(cwd)] = {"passed": key}
        sf.write_text(json.dumps(st), "utf-8")
        _log(agent, cwd, "pass", 0)
        return 0, ""
    if blocks >= MAX_BLOCKS:
        _log(agent, cwd, "let-through", len(found))
        return 0, ""
    st[str(cwd)] = {"key": key, "blocks": blocks + 1}
    sf.write_text(json.dumps(st), "utf-8")
    _log(agent, cwd, "sent-back", len(found))
    msg = ("Not finished: Scranton checked what your branch changed and found this. Fix it before you hand in or reply "
           "(if one is not yours to fix, say so in your hand-in).\n" + "\n".join(found))
    return 2, msg


def main() -> int:
    agent = sys.argv[sys.argv.index("--agent") + 1] if "--agent" in sys.argv[:-1] else "agent"
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    try:
        code, msg = run(agent, payload if isinstance(payload, dict) else {})
    except Exception as e:                           # a broken check must never stop a teammate from working
        try:
            _log(agent, Path("."), f"error: {type(e).__name__}", 0)
        except Exception:
            pass
        return 0
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
