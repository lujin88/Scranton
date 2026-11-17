"""A stalled presence loop must not mark every teammate disconnected."""
import time

import mcp_bridge
import app


def _reset():
    mcp_bridge._presence.clear()
    mcp_bridge._activity.clear()
    mcp_bridge._activity_ts.clear()


def test_stall_keeps_live_teammates_online():
    """Mac sleep / a stuck loop of 25s: last heartbeat is at the start of the stall.
    PRESENCE_TIMEOUT is 10s, so a snapshot taken before forgiveness looks empty and the
    leave path posts "pm disconnected" for the whole team. Forgive first, then snapshot."""
    _reset()
    now = 1_800_000_000.0
    stall = 25.0
    mcp_bridge._presence.update({"pm": now - stall, "dev": now - stall, "ghost": now - 50})
    mcp_bridge._activity.update({"pm": True, "dev": True})
    mcp_bridge._activity_ts.update({"pm": now - stall, "dev": now - stall})

    # Don't call _snapshot_presence here: it expires activity as a side effect.
    before = {n for n, ts in mcp_bridge._presence.items() if now - ts < mcp_bridge.PRESENCE_TIMEOUT}
    assert before == set()   # this is the bug if the loop snapshots first

    assert app._forgive_stalled_heartbeats(now, now - stall, crash_timeout=15)
    online, active = app._snapshot_presence(now)
    assert online == {"pm", "dev"}
    assert active == {"pm", "dev"}
    assert now - mcp_bridge._presence["ghost"] == 50  # a real crash before the stall stays gone


def test_no_stall_does_not_revive_a_real_crash():
    _reset()
    now = time.time()
    mcp_bridge._presence["pm"] = now - 20
    assert app._forgive_stalled_heartbeats(now, now - 3, crash_timeout=15) is False
    online, _ = app._snapshot_presence(now)
    assert online == set()
