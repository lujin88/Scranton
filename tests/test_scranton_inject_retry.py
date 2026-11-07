"""A mention that can't be typed (agent's terminal shows a question) is kept and retried."""
import json, threading, time
from pathlib import Path
import wrapper


def test_blocked_mention_is_requeued_then_delivered(tmp_path, monkeypatch):
    q = tmp_path / "pm_queue.jsonl"
    q.write_text(json.dumps({"channel": "lu-portfolio"}) + "\n", "utf-8")
    posts, calls = [], []
    monkeypatch.setattr(wrapper, "_post", lambda *a: posts.append(a))
    monkeypatch.setattr(wrapper, "_fetch_role", lambda *a: "")
    monkeypatch.setattr(wrapper, "_fetch_active_rules", lambda *a: None)
    real_sleep = time.sleep
    monkeypatch.setattr(wrapper.time, "sleep", lambda s: real_sleep(0.01))

    def inject(text):
        calls.append(text)
        return "question" if len(calls) == 1 else True

    t = threading.Thread(target=wrapper._queue_watcher, args=(lambda: ("pm", q), inject),
                         kwargs={"team_brief": "BRIEF"}, daemon=True)
    t.start()
    for _ in range(300):
        if len(calls) >= 2:
            break
        real_sleep(0.01)
    assert len(calls) == 2, calls
    assert len(posts) == 1 and "waiting on a question" in posts[0][-1]
    # the brief wasn't delivered the first time, so the retry still carries it
    assert "TEAM: BRIEF" in calls[1]
    real_sleep(0.05)
    assert not q.exists() or q.read_text("utf-8") == ""
