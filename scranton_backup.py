"""Scranton: keep a copy of the chat history, like WeChat's backup.

- Every day one .zip goes into a folder Lu picks (iCloud Drive "Scranton Backups" when
  iCloud is there). The newest 14 stay; older Scranton backups in that folder are removed.
- "Export chat history" downloads the same .zip.
- "Import chat history" checks a .zip, backs up what is here now, and puts the imported
  files in place the next time Scranton starts (the server holds the history in memory).

Agent tokens (registry.json), queues, logs and run state are never in a backup.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import threading
import time
import zipfile
from datetime import date
from pathlib import Path

from safe_io import atomic_write

KEEP = 14
MAX_IMPORT = 1024 * 1024 * 1024  # 1 GB unpacked
NAME_RE = re.compile(r"^Scranton chat history (\d{4}-\d{2}-\d{2})\.zip$")
SKIP_FILES = {"registry.json", "mcp_cursors.json", "backup.json"}
SKIP_DIRS = {"run", "logs", "import-pending", "import-old", "provider-config"}
# Belt and braces: never copy a settings-type file that holds a credential.
SECRET_RE = re.compile(rb'(?i)(bearer\s+[a-z0-9]|"authorization"|"(?:access_|api_|session_)?token"\s*:|"api[_-]?key"\s*:)')
SKIP_SUFFIX = (".taking", ".lock", ".tmp", "_queue.jsonl", ".corrupt")
README = """Scranton chat history
=====================

This file is a copy of your Scranton chat history: every message in every channel,
the files and pictures sent in chat, and your Scranton settings (channels, teammates,
schedules, profile picture).

It does not hold passwords or agent sign-ins.

To put it back: Scranton > Settings > Chat history > Import chat history.
"""

_lock = threading.Lock()
_data = Path("./data")
_uploads = Path("./uploads")


def setup(data_dir: str | Path, upload_dir: str | Path):
    global _data, _uploads
    _data, _uploads = Path(data_dir), Path(upload_dir)


def default_folder() -> Path:
    icloud = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if icloud.is_dir():
        return icloud / "Scranton Backups"
    return Path.home() / "Documents" / "Scranton Backups"


def _settings_path() -> Path:
    return _data / "backup.json"


def settings() -> dict:
    s = {"enabled": True, "folder": "", "last": 0, "last_file": "", "error": ""}
    try:
        s.update(json.loads(_settings_path().read_text("utf-8")))
    except (OSError, ValueError):
        pass
    s["default_folder"] = str(default_folder())
    s["pending_import"] = (_data / "import-pending").is_dir()
    return s


def _save(s: dict):
    keep = {k: s[k] for k in ("enabled", "folder", "last", "last_file", "error") if k in s}
    atomic_write(_settings_path(), json.dumps(keep, ensure_ascii=False, indent=2))


def set_settings(enabled: bool | None = None, folder: str | None = None) -> dict:
    s = settings()
    if enabled is not None:
        s["enabled"] = bool(enabled)
    if folder is not None:
        folder = folder.strip()
        if folder and not Path(folder).expanduser().is_absolute():
            raise ValueError("Use a full folder path, like /Users/you/Documents/Backups")
        s["folder"] = folder
    _save(s)
    return settings()


def folder() -> Path:
    f = settings().get("folder") or ""
    return Path(f).expanduser() if f else default_folder()


def _files():
    """(path on disk, name in the zip) for everything that belongs in a backup."""
    for base, prefix in ((_data, "data"), (_uploads, "uploads")):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            rel = p.relative_to(base)
            if prefix == "data" and (rel.parts[0] in SKIP_DIRS or rel.name in SKIP_FILES):
                continue
            if rel.name.endswith(SKIP_SUFFIX):
                continue
            if prefix == "data" and p.suffix in (".json", ".toml", ".env", ".cfg", ".ini", ".yaml", ".yml") and _has_secret(p):
                continue
            yield p, f"{prefix}/{rel.as_posix()}"


def _has_secret(p: Path) -> bool:
    try:
        return bool(SECRET_RE.search(p.read_bytes()[:2_000_000]))
    except OSError:
        return True


def write_zip(out) -> int:
    """Write the backup into a path or file object. Returns the number of files."""
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        z.writestr("scranton-backup.json", json.dumps({"version": 1, "made": time.time()}))
        for p, name in _files():
            try:
                z.write(p, name)
                n += 1
            except OSError:
                continue
    return n


def export_bytes() -> bytes:
    buf = io.BytesIO()
    with _lock:
        write_zip(buf)
    return buf.getvalue()


def file_name(day: date | None = None) -> str:
    return f"Scranton chat history {(day or date.today()).isoformat()}.zip"


def backup_now() -> dict:
    """Make today's backup (replacing an earlier one from today) and keep the newest 14."""
    s = settings()
    dest = folder()
    with _lock:
        try:
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / file_name()
            tmp = target.with_name(target.name + ".tmp")
            write_zip(tmp)
            tmp.replace(target)
            _prune(dest)
            s.update(last=time.time(), last_file=str(target), error="")
        except OSError as e:
            s["error"] = f"Couldn't save to {dest}: {e.strerror or e}"
        _save(s)
    return settings()


def _prune(dest: Path):
    ours = sorted((p for p in dest.iterdir() if NAME_RE.match(p.name)), key=lambda p: p.name)
    for old in ours[:-KEEP]:
        old.unlink(missing_ok=True)


def due() -> bool:
    s = settings()
    if not s.get("enabled"):
        return False
    return not (folder() / file_name()).exists()


def start_daily(interval: int = 3600):
    def loop():
        time.sleep(60)  # let the server finish starting
        while True:
            try:
                if due():
                    backup_now()
            except Exception:
                pass
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="scranton-backup").start()


# --- Import -----------------------------------------------------------------

def stage_import(raw: bytes) -> dict:
    """Check an uploaded backup and stage it. Applied by apply_pending() on next start."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError("This isn't a Scranton chat history file (.zip).")
    names = z.namelist()
    if "data/agentchattr_log.jsonl" not in names and "data/room_log.jsonl" not in names:
        raise ValueError("This .zip has no Scranton chat history in it.")
    total = 0
    picked = []
    for info in z.infolist():
        name = info.filename
        if info.is_dir() or name in ("README.txt", "scranton-backup.json"):
            continue
        parts = Path(name).parts
        if (name.startswith("/") or ".." in parts or len(parts) < 2
                or parts[0] not in ("data", "uploads") or "\\" in name):
            raise ValueError(f"Unexpected file in the backup: {name}")
        if parts[0] == "data" and (parts[1] in SKIP_DIRS or Path(name).name in SKIP_FILES):
            continue
        total += info.file_size
        if total > MAX_IMPORT:
            raise ValueError("This backup is larger than 1 GB.")
        picked.append(info)
    with _lock:
        pending = _data / "import-pending"
        if pending.exists():
            shutil.rmtree(pending)
        pending.mkdir(parents=True)
        for info in picked:
            out = pending / info.filename
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    # Keep a copy of what is here now before anything is replaced.
    backup_now()
    return {"ok": True, "files": len(picked)}


def cancel_import():
    with _lock:
        pending = _data / "import-pending"
        if pending.is_dir():
            shutil.rmtree(pending)


def apply_pending(data_dir: str | Path, upload_dir: str | Path) -> int:
    """Called at start, before the history is loaded. Old files move to data/import-old."""
    data_dir, upload_dir = Path(data_dir), Path(upload_dir)
    pending = data_dir / "import-pending"
    if not pending.is_dir():
        return 0
    old = data_dir / "import-old" / time.strftime("%Y%m%d-%H%M%S")
    moved = 0
    for src in sorted(pending.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(pending)
        root = data_dir if rel.parts[0] == "data" else upload_dir
        target = root.joinpath(*rel.parts[1:])
        if target.exists():
            keep = old / rel
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(keep))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(target))
        moved += 1
    shutil.rmtree(pending, ignore_errors=True)
    return moved
