"""Report → Tokens: read Claude Code / Codex logs, attribute to teammate by sender, to task by thread."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scranton_tokens as tk


class Tokens(unittest.TestCase):
    def test_attribution(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            cl = home / ".claude" / "projects" / "x"; cl.mkdir(parents=True)
            iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))  # noqa: E731
            lines = [
                {"type": "assistant", "timestamp": iso(now - 50), "requestId": "r1",
                 "message": {"id": "m1", "content": [{"type": "tool_use", "input": {"sender": "pm", "message": "hi"}}],
                             "usage": {"input_tokens": 10, "cache_creation_input_tokens": 90, "cache_read_input_tokens": 1000, "output_tokens": 50}}},
                # same message streamed twice: counted once
                {"type": "assistant", "timestamp": iso(now - 50), "requestId": "r1",
                 "message": {"id": "m1", "usage": {"input_tokens": 10, "cache_creation_input_tokens": 90, "cache_read_input_tokens": 1000, "output_tokens": 50}}},
            ]
            (cl / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
            cx = home / ".codex" / "sessions" / "2026" / "11" / "09"; cx.mkdir(parents=True)
            rows = [{"timestamp": iso(now - 40), "type": "response_item",
                     "payload": {"type": "function_call", "arguments": json.dumps({"sender": "visual", "message": "x"})}},
                    {"timestamp": iso(now - 30), "type": "event_msg", "payload": {"type": "token_count", "info": {
                        "last_token_usage": {"input_tokens": 500, "cached_input_tokens": 400, "output_tokens": 20, "reasoning_output_tokens": 30}}}}]
            (cx / "rollout-a.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
            msgs = [
                {"id": 1, "sender": "Lu", "text": "@pm do the thing", "channel": "c", "timestamp": now - 100},
                {"id": 2, "sender": "pm", "text": "@visual draw it", "channel": "c", "reply_to": 1, "timestamp": now - 45},
            ]
            team = {"pm": {"command": "claude", "model": "opus"}, "visual": {"command": "codex"}, "web": {"command": "agent"}}
            tk._cache.clear()
            r = tk.build(msgs, team, "Lu", 7, home=home)
            self.assertEqual(r["total"], 10 + 90 + 1000 + 50 + 100 + 400 + 50)
            a = {x["agent"]: x["tokens"] for x in r["agents"]}
            self.assertEqual(a, {"pm": 1150, "visual": 550})
            self.assertEqual(len(r["tasks"]), 1)                    # both went to thread #1
            self.assertEqual(r["tasks"][0]["id"], 1)
            self.assertEqual(r["tasks"][0]["agents"], ["pm", "visual"])
            self.assertEqual(r["not_counted"], ["web"])
            self.assertTrue(r["tips"])

    def test_incremental_no_double_count(self):
        now = time.time()
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))  # noqa: E731
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            cx = home / ".codex" / "sessions" / "2026"; cx.mkdir(parents=True)
            f = cx / "rollout-b.jsonl"
            call = {"timestamp": iso(now - 40), "type": "response_item",
                    "payload": {"type": "function_call", "arguments": json.dumps({"sender": "visual"})}}
            tc = lambda n: {"timestamp": iso(now - 30), "type": "event_msg", "payload": {"type": "token_count",  # noqa: E731
                            "info": {"last_token_usage": {"input_tokens": n, "cached_input_tokens": 0, "output_tokens": 0}}}}
            f.write_text(json.dumps(call) + "\n" + json.dumps(tc(100)))       # last line not yet terminated
            team = {"visual": {"command": "codex"}}
            tk._cache.clear(); tk._files_seen.clear()
            self.assertEqual(tk.build([], team, "Lu", 7, home=home)["total"], 100)
            with open(f, "a") as fh:
                fh.write("\n" + json.dumps(tc(5)) + "\n")
            tk._cache.clear()
            self.assertEqual(tk.build([], team, "Lu", 7, home=home)["total"], 105)
            tk._cache.clear()
            self.assertEqual(tk.build([], team, "Lu", 7, home=home)["total"], 105)

    def test_sender_from_own_calls_not_from_chat_read_results(self):
        now = time.time()
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))  # noqa: E731
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            cl = home / ".claude" / "projects" / "x"; cl.mkdir(parents=True)
            read_result = json.dumps([{"sender": "pm", "text": "a"}, {"sender": "pm", "text": "b"}, {"sender": "pm", "text": "c"}])
            lines = [
                {"type": "assistant", "timestamp": iso(now - 60), "requestId": "r1",
                 "message": {"id": "m1", "content": [{"type": "tool_use", "input": {"sender": "copy", "channel": "x"}}],
                             "usage": {"input_tokens": 1, "output_tokens": 1}}},
                {"type": "user", "timestamp": iso(now - 59),
                 "message": {"content": [{"type": "tool_result", "content": read_result}]}},
            ]
            (cl / "s.jsonl").write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in lines) + "\n")
            cx = home / ".codex" / "sessions" / "2026"; cx.mkdir(parents=True)
            rows = [{"timestamp": iso(now - 40), "type": "response_item",
                     "payload": {"type": "function_call", "arguments": json.dumps({"sender": "visual"})}},
                    {"timestamp": iso(now - 39), "type": "response_item",
                     "payload": {"type": "function_call_output", "output": read_result}},
                    {"timestamp": iso(now - 30), "type": "event_msg", "payload": {"type": "token_count", "info": {
                        "last_token_usage": {"input_tokens": 5, "cached_input_tokens": 0, "output_tokens": 0}}}}]
            (cx / "rollout-c.jsonl").write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in rows) + "\n")
            team = {"pm": {}, "copy": {}, "visual": {"command": "codex"}}
            tk._cache.clear(); tk._files_seen.clear()
            a = {x["agent"]: x["tokens"] for x in tk.build([], team, "Lu", 7, home=home)["agents"]}
            self.assertEqual(a, {"copy": 2, "visual": 5})

    def test_codex_posting_as_codex_is_found_by_its_worktree(self):
        now = time.time()
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))  # noqa: E731
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            cx = home / ".codex" / "sessions" / "2026"; cx.mkdir(parents=True)
            rows = [{"timestamp": iso(now - 50), "type": "session_meta", "payload": {"cwd": "/Users/lu/LuJin-Portfolio-worktrees/motion"}},
                    {"timestamp": iso(now - 40), "type": "response_item",
                     "payload": {"type": "custom_tool_call", "input": json.dumps({"sender": "codex"})}},
                    {"timestamp": iso(now - 30), "type": "event_msg", "payload": {"type": "token_count", "info": {
                        "last_token_usage": {"input_tokens": 7, "cached_input_tokens": 0, "output_tokens": 0}}}}]
            (cx / "rollout-d.jsonl").write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in rows) + "\n")
            tk._cache.clear(); tk._files_seen.clear()
            r = tk.build([], {"motion": {"command": "codex"}}, "Lu", 7, home=home)
            self.assertEqual({x["agent"]: x["tokens"] for x in r["agents"]}, {"motion": 7})


if __name__ == "__main__":
    unittest.main()
