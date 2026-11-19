"""Preview: open a page or a file that lives on the Scranton machine from any device.

Lu, 2026-11-19: she works on the MacBook while the team runs on the Mac mini; a teammate's
"http://localhost:4661/index.html" or "/Users/lu/.scranton/OUTBOX/x.png" points at the wrong
computer there, and on the phone at nothing.

Two things can be previewed, both read-only (GET and HEAD):
  /preview/<key>/p/<port>/<path>   a page served on this machine's localhost
  /preview/<key>/f/<absolute path> a file or folder under one of the allowed folders

How it is kept safe:
  - <key> is derived from a long random secret in data/preview.key, one key per port and one per
    allowed folder. Only the signed-in Scranton page can ask for an address, so it cannot be guessed
    by another web page or machine, and a page inside one preview cannot open the others.
  - Every answer carries "Content-Security-Policy: sandbox": the previewed page runs as a
    stranger to Scranton. A teammate's page (or a script it loads from a CDN) cannot read the
    Scranton session or call its API as the owner.
  - "Referrer-Policy: no-referrer", so the key in the address is not sent to sites the page loads from.
  - Ports: only the usual development ranges, never Scranton's own ports. Files: only inside the
    allowed folders after resolving symlinks, never dot-files or anything that looks like a secret.
"""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote

DEFAULT_PORTS = ["3000-3999", "4000-4999", "5173-5179", "8000-8099", "8080-8089"]
SECRET_NAME = re.compile(r"(^\.|token|secret|credential|password|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$|\.keychain|\.sqlite$|\.db$)", re.I)
TEXT_AS_PLAIN = {".md", ".txt", ".log", ".json", ".toml", ".yml", ".yaml", ".csv", ".py", ".ts", ".tsx", ".jsx", ".sh"}
HEADERS = {
    # No allow-same-origin: the page gets an origin of its own and cannot touch Scranton's.
    "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads allow-pointer-lock allow-presentation",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    # A sandboxed page loads its own scripts and fonts as a foreign origin; the key in the path is the gate.
    "Access-Control-Allow-Origin": "*",
    "Cross-Origin-Resource-Policy": "cross-origin",
}
REWRITE_MAX = 6 * 1024 * 1024


def key(data_dir: str | Path) -> str:
    """The secret that every preview address starts with. Made once, kept in data/preview.key."""
    p = Path(data_dir) / "preview.key"
    try:
        k = p.read_text("utf-8").strip()
        if len(k) >= 32:
            return k
    except OSError:
        pass
    k = secrets.token_urlsafe(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(k)
    return k


def key_for(data_dir: str | Path, scope: str) -> str:
    """The key for one port ("p:4661") or one allowed folder ("f:/Users/lu/proj"). A previewed page
    can read its own address, so it knows its own key; with one key per port and per folder that is
    all it knows, and a script inside one preview cannot walk into the others."""
    import hashlib, hmac
    return hmac.new(key(data_dir).encode(), scope.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def root_of(cfg: dict, p: Path) -> Path | None:
    for r in roots(cfg):
        if p == r or r in p.parents:
            return r
    return None


def _ranges(spec) -> list[tuple[int, int]]:
    out = []
    for s in spec or []:
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", str(s))
        if m:
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            out.append((min(a, b), max(a, b)))
    return out


def own_ports(cfg: dict) -> set[int]:
    """Scranton's own ports: previewing those would hand a sandboxed page a way back in."""
    out = set()
    for sec, keys in (("server", ("port",)), ("mcp", ("http_port", "sse_port", "port"))):
        for k in keys:
            try:
                out.add(int((cfg.get(sec, {}) or {}).get(k)))
            except (TypeError, ValueError):
                pass
    return out


def port_ok(cfg: dict, port: int) -> bool:
    spec = (cfg.get("preview", {}) or {}).get("ports", DEFAULT_PORTS)
    return port not in own_ports(cfg) and any(a <= port <= b for a, b in _ranges(spec))


def roots(cfg: dict) -> list[Path]:
    """Folders whose files may be previewed: where the teammates work, their hand-over folders,
    the uploads, and whatever [preview] roots adds."""
    want: list[str] = ["~/.scranton/OUTBOX", str((cfg.get("images", {}) or {}).get("upload_dir", "./uploads"))]
    for a in (cfg.get("agents", {}) or {}).values():
        cwd = str(a.get("cwd", "") or "").strip()
        if cwd:
            want.append(cwd)
            if a.get("worktree"):
                want.append(cwd.rstrip("/") + "-worktrees")
    want += [str(x) for x in (cfg.get("preview", {}) or {}).get("roots", []) or []]
    out: list[Path] = []
    for w in want:
        try:
            p = Path(os.path.expanduser(w)).resolve()
        except OSError:
            continue
        # never a whole home folder or the disk: a root that broad would expose everything in it
        if p in (Path.home().resolve(), Path("/")) or len(p.parts) < 3:
            continue
        if p not in out:
            out.append(p)
    return out


def file_target(cfg: dict, raw: str) -> tuple[Path | None, str]:
    """(file or folder, "") when `raw` may be previewed, else (None, why not)."""
    try:
        p = Path(os.path.expanduser("/" + raw.lstrip("/") if not raw.startswith("~") else raw)).resolve()
    except (OSError, RuntimeError):
        return None, "not a path"
    for r in roots(cfg):
        if p == r or r in p.parents:
            below = p.relative_to(r).parts
            if any(SECRET_NAME.search(part) for part in below):
                return None, "this file is not shown in previews"
            if not p.exists():
                return None, "not found"
            return p, ""
    return None, "outside the folders previews may open (add the folder to [preview] roots in config.local.toml)"


def url_for_file(k: str, path: Path | str) -> str:
    return f"/preview/{k}/f/" + quote(str(path).lstrip("/"))


def rewrite(body: bytes, ctype: str, prefix: str) -> bytes:
    """A page under /preview/<key>/p/<port>/ still asks for "/assets/app.js" from the top of the
    site. Point those at the previewed port: root-relative src/href in HTML, url(/…) in CSS, and
    the "/_next/" Next.js builds its chunk addresses from."""
    if len(body) > REWRITE_MAX:
        return body
    try:
        t = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    c = ctype.lower()
    if "html" in c:
        t = re.sub(r"""(\b(?:src|href|action|poster|data-src)\s*=\s*["'])/(?!/)""", rf"\1{prefix}/", t)
        t = re.sub(r"""(\bsrcset\s*=\s*["'])/(?!/)""", rf"\1{prefix}/", t)
    if "html" in c or "css" in c:
        t = re.sub(r"""(url\(\s*["']?)/(?!/)""", rf"\1{prefix}/", t)
    if "html" in c or "javascript" in c:
        t = t.replace('"/_next/', f'"{prefix}/_next/').replace("'/_next/", f"'{prefix}/_next/")
    return t.encode("utf-8")


def listing(k: str, folder: Path) -> str:
    """A plain list of what is in a folder that has no index.html."""
    import html
    rows = []
    try:
        items = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        items = []
    for p in items:
        if SECRET_NAME.search(p.name):
            continue
        name = p.name + ("/" if p.is_dir() else "")
        rows.append(f'<li><a href="{html.escape(url_for_file(k, p))}">{html.escape(name)}</a></li>')
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(folder.name)}</title>"
            "<style>body{font:15px/1.6 -apple-system,system-ui,sans-serif;margin:24px;background:#111;color:#eee}"
            "a{color:#8ab4ff;text-decoration:none}li{list-style:none;padding:6px 0}h1{font-size:16px;color:#aaa;font-weight:500}</style>"
            f"<h1>{html.escape(str(folder))}</h1><ul>{''.join(rows) or '<li>Empty folder</li>'}</ul>")
