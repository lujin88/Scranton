"""After a restart, an agent picks up an unanswered request by itself."""
import io, json, time
import wrapper


def _run(tmp_path, monkeypatch, msgs, age=60):
    q = tmp_path / "pm_queue.jsonl"
    (tmp_path / "run").mkdir()
    at = time.time() - age
    (tmp_path / "run" / "pm.work.json").write_text(json.dumps({"channel": "lu-portfolio", "thread": None, "at": at}))
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=5: io.BytesIO(json.dumps(msgs(at)).encode()))
    wrapper._resume_unfinished(q, "pm", 8300, lambda: "tok", delay=0)
    return q


def test_unanswered_request_is_resumed(tmp_path, monkeypatch):
    q = _run(tmp_path, monkeypatch, lambda at: [{"sender": "Lu", "text": "@pm do it", "timestamp": at - 1}])
    line = json.loads(q.read_text().strip())
    assert line["channel"] == "lu-portfolio" and "restarted" in line["prompt"]


def test_answered_request_is_left_alone(tmp_path, monkeypatch):
    q = _run(tmp_path, monkeypatch, lambda at: [{"sender": "pm", "text": "done", "timestamp": at + 5}])
    assert not q.exists()


def test_old_work_is_ignored(tmp_path, monkeypatch):
    q = _run(tmp_path, monkeypatch, lambda at: [], age=3 * 24 * 3600)
    assert not q.exists()
