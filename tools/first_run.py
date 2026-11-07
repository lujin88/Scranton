"""Answer the CLIs' one-time first-run questions before Scranton starts a teammate.

A teammate runs in a background terminal nobody looks at. If its CLI stops on
"Do you trust this folder?" or Claude's one-time "bypass permissions" warning,
it waits there forever. Lu already decided both (her own project folders, and
permissions = "full"), so record those answers the way each CLI stores them.

    python tools/first_run.py <command> <folder> <full|ask>

Only adds missing entries; never removes or rewrites anything else. Writes go
to a temp file that replaces the original, so a crash can't leave half a file.
Unknown file layouts are left alone (the CLI will then just ask as before).
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_json(path: Path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8") or "{}")
    except (OSError, ValueError):
        return None  # unreadable: don't touch it
    return data if isinstance(data, dict) else None


def claude(folder: str, full: bool, home: Path) -> list[str]:
    done = []
    state_path = home / ".claude.json"
    state = _load_json(state_path)
    if state is not None:
        changed = False
        proj = state.setdefault("projects", {}).setdefault(folder, {})
        if isinstance(proj, dict) and not proj.get("hasTrustDialogAccepted"):
            proj["hasTrustDialogAccepted"] = True
            changed = True
        if full and not state.get("bypassPermissionsModeAccepted"):
            state["bypassPermissionsModeAccepted"] = True
            changed = True
        if changed:
            _atomic_write(state_path, json.dumps(state, indent=2, ensure_ascii=False) + "\n")
            done.append("claude: folder trusted" + (", full-permission warning accepted" if full else ""))
    if full:
        settings_path = home / ".claude" / "settings.json"
        settings = _load_json(settings_path)
        if settings is not None and not settings.get("skipDangerousModePermissionPrompt"):
            settings["skipDangerousModePermissionPrompt"] = True
            _atomic_write(settings_path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
            done.append("claude: full-permission prompt off")
    return done


def codex(folder: str, home: Path) -> list[str]:
    path = home / ".codex" / "config.toml"
    text = path.read_text("utf-8") if path.exists() else ""
    header = f'[projects."{folder}"]'
    if header in text or '"' in folder or "\n" in folder:
        return []
    block = f'\n{header}\ntrust_level = "trusted"\n'
    _atomic_write(path, (text.rstrip("\n") + "\n" if text else "") + block)
    return ["codex: folder trusted"]


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    command, folder, perm = Path(argv[1]).name, os.path.realpath(os.path.expanduser(argv[2])), argv[3]
    home = Path(os.environ.get("SCRANTON_HOME") or Path.home())
    try:
        if command == "claude":
            done = claude(folder, perm == "full", home)
        elif command == "codex":
            done = codex(folder, home)
        else:
            done = []  # Cursor: --force and --approve-mcps cover it
    except OSError as e:
        print(f"  first-run setup skipped: {e}")
        return 0
    for line in done:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
