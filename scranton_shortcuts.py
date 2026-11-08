"""Scranton: saved messages Lu sends often, picked from the bottom of the message box."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from safe_io import atomic_write

MAX = 20
_lock = threading.Lock()
_path = Path(__file__).resolve().parent / "data" / "shortcuts.json"

DEFAULTS = [
    {"label": "What needs me",
     "text": "@pm 现在有哪些事要我定？把待问清单一次发我：编号列表，每条一行（问题｜选项 A/B/C｜团队建议），"
             "我一句话回答。没有就说没有。"},
    {"label": "Clean up my Mac",
     "text": "@ops 清理这台 Mac，再整理移动硬盘。\n"
             "1. 先列出能清的：缓存、下载文件夹、旧的 node_modules 和构建产物、重复文件、废纸篓。每类写大小和路径。\n"
             "2. 不直接删任何东西：要删的移到所在文件夹的 _to_delete/，列给我，我确认了再删。\n"
             "3. 不能删但占地方的（照片、视频、旧项目、安装包）移到移动硬盘，按「类别/年份」放。同名不覆盖；"
             "大小核对一致后，原文件才移进 _to_delete/。\n"
             "4. 移动硬盘也整理：乱放的归到对应文件夹，重复的标出来，同样不删。\n"
             "5. 硬盘没插、空间不够、或者拿不准的，先问我。\n"
             "做完给我一张表：省出多少空间｜移了什么、到哪｜要我确认的。"},
]


def setup(data_dir):
    global _path
    _path = Path(data_dir) / "shortcuts.json"


def load() -> list[dict]:
    try:
        items = json.loads(_path.read_text("utf-8"))
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
    except (OSError, ValueError):
        pass
    return [dict(d) for d in DEFAULTS]


def save(items) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("Expected a list")
    clean = []
    for i in items[:MAX]:
        if not isinstance(i, dict):
            continue
        label = str(i.get("label", "")).strip()[:40]
        text = str(i.get("text", "")).strip()[:4000]
        if label and text:
            clean.append({"label": label, "text": text})
    with _lock:
        atomic_write(_path, json.dumps(clean, ensure_ascii=False, indent=2))
    return clean
