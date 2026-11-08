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
     "text": "@pm 现在有哪些事要我定？把待问清单一次发我：每个问题一行，下面每个选项单独一行写成「A. …」「B. …」"
             "（团队建议放第一个并标推荐），我点按钮回答。没有就说没有。"},
    {"label": "Clean up my Mac",
     "text": "@ops 清理这台 Mac，再整理移动硬盘。\n"
             "1. 先列出能清的：缓存、下载文件夹、旧的 node_modules 和构建产物、重复文件、废纸篓。每类写大小和路径。\n"
             "2. 不直接删任何东西：要删的移到所在文件夹的 _to_delete/，列给我，我确认了再删。\n"
             "3. 不能删但占地方的（照片、视频、旧项目、安装包）移到移动硬盘，按「类别/年份」放。同名不覆盖；"
             "大小核对一致后，原文件才移进 _to_delete/。\n"
             "4. 移动硬盘也整理：乱放的归到对应文件夹，重复的标出来，同样不删。\n"
             "5. 硬盘没插、空间不够、或者拿不准的，先问我。\n"
             "做完给我一张表：省出多少空间｜移了什么、到哪｜要我确认的。"},
    {"label": "Product review",
     "text": "@pm 组织团队，像一个成熟、优秀的产品团队那样，从各个维度 review 这个频道的产品，然后出一份报告和建议。\n"
             "1. 维度：产品定位和核心任务、主要流程、信息架构、交互、视觉一致性、文案、可访问性、性能、可靠性、安全与权限、代码质量。"
             "每个维度派最合适的队友，你来分工。\n"
             "2. 每条发现写：问题｜证据（截图、文件路径或复现步骤）｜影响｜建议｜工作量。没有证据的标「推断」，不编数字。\n"
             "3. 只看和提建议，不改代码、不开 PR。\n"
             "4. 最后你汇总成一份报告：按影响排序的前 5 件事，再加现在 / 下一步 / 以后，和明确不做的事。发我链接。"},
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
