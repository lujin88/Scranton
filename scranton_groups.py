"""Channel groups in the sidebar (Lu, 11-25: "加一个 project 或者 group… 有一些我可能就 archive 掉的
channel，我可以自己命名").

A group is a name she chose and the channels under it, shown as a collapsible heading below the
ungrouped channels. Grouping changes only where a channel sits in her sidebar: nothing about the
channel, its teammates or its work. Kept in room settings as
`channel_groups: [{"id": 1, "name": "Archive", "channels": ["ai-pet"], "collapsed": true}]`.
"""
from __future__ import annotations

MAX_GROUPS = 12
MAX_NAME = 32


def _clean(groups) -> list[dict]:
    out = []
    for g in groups or []:
        if isinstance(g, dict) and str(g.get("name") or "").strip():
            out.append({"id": int(g.get("id") or 0), "name": str(g["name"]).strip()[:MAX_NAME],
                        "channels": [str(c) for c in g.get("channels") or []], "collapsed": bool(g.get("collapsed"))})
    return out


def _name_ok(groups: list[dict], name: str, but: int = 0) -> bool:
    n = name.strip().lower()
    return bool(n) and all(g["name"].lower() != n or g["id"] == but for g in groups)


def can_group(channel: str, channels: list[str]) -> bool:
    return channel in channels and not channel.startswith("dm-")


def apply(groups, channels: list[str], action: str, body: dict) -> tuple[list[dict], str]:
    """The groups after one change, and an error in plain words ("" when it went through)."""
    gs = _clean(groups)
    by = {g["id"]: g for g in gs}
    gid = int(body.get("id") or 0)
    name = str(body.get("name") or "").strip()[:MAX_NAME]
    ch = str(body.get("channel") or "")

    def take_out(c: str) -> None:
        for g in gs:
            g["channels"] = [x for x in g["channels"] if x != c]

    if action == "create":
        if not _name_ok(gs, name):
            return gs, "That name is empty or already used."
        if len(gs) >= MAX_GROUPS:
            return gs, f"{MAX_GROUPS} groups at most."
        new = {"id": max([g["id"] for g in gs] + [0]) + 1, "name": name, "channels": [], "collapsed": False}
        if ch:
            if not can_group(ch, channels):
                return gs, "That channel can't go in a group."
            take_out(ch)
            new["channels"] = [ch]
        gs.append(new)
    elif action == "rename":
        if gid not in by or not _name_ok(gs, name, gid):
            return gs, "That name is empty or already used."
        by[gid]["name"] = name
    elif action == "delete":
        if gid not in by:
            return gs, "No such group."
        gs = [g for g in gs if g["id"] != gid]              # its channels go back to the main list
    elif action == "move":
        if not can_group(ch, channels) or (gid and gid not in by):
            return gs, "That channel can't go there."
        take_out(ch)
        if gid:
            by[gid]["channels"].append(ch)
    elif action == "collapse":
        if gid not in by:
            return gs, "No such group."
        by[gid]["collapsed"] = bool(body.get("on"))
    else:
        return gs, "action is create, rename, delete, move or collapse"
    return gs, ""


def renamed(groups, old: str, new: str) -> list[dict]:
    gs = _clean(groups)
    for g in gs:
        g["channels"] = [new if c == old else c for c in g["channels"]]
    return gs


def removed(groups, name: str) -> list[dict]:
    gs = _clean(groups)
    for g in gs:
        g["channels"] = [c for c in g["channels"] if c != name]
    return gs
