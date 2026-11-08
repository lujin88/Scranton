"""After a restart, an agent picks up an unanswered request by itself."""
import io, json, time, unittest
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


class TakeQueueTest(unittest.TestCase):
    def test_leftover_taking_is_kept_and_merged(self):
        import tempfile
        from pathlib import Path
        import wrapper
        with tempfile.TemporaryDirectory() as d:
            q = Path(d) / "pm_queue.jsonl"
            t = Path(d) / "pm_queue.jsonl.taking"
            t.write_text('{"n":1}\n')          # left by a stop mid-delivery
            q.write_text('{"n":2}\n{"n":3}\n')
            self.assertEqual(wrapper._take_queue(q, t), 0)
            self.assertEqual(t.read_text().split(), ['{"n":1}', '{"n":2}', '{"n":3}'])
            self.assertFalse(q.exists())
            q.write_text("".join(f'{{"n":{i}}}\n' for i in range(4, 10)))
            self.assertEqual(wrapper._take_queue(q, t, keep=5), 4)
            self.assertEqual(len(t.read_text().split()), 5)
