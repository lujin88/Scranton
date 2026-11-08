"""Fresh-session handover: ask for a note, wait for it, start clean, carry the note over."""
import tempfile
import time
import unittest
from pathlib import Path

import wrapper as w


class HandoverTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        w._HANDOVER.update({"handoff_dir": self.dir, "busy": None, "command": "claude"})

    def fake_agent(self, write=True):
        sent = []
        def inject(text):
            sent.append(text)
            if text.startswith("Scranton: before your next message") and write:
                time.sleep(0.05)
                (self.dir / "dev.md").write_text("Working on #77.\nNext: screenshots.", "utf-8")
            return True
        return inject, sent

    def test_due(self):
        s = {"enabled": True, "hours": 4, "wakes": 40}
        self.assertFalse(w._handover_due({**s, "enabled": False}, 0, 999))
        self.assertTrue(w._handover_due(s, time.time(), 40))
        self.assertTrue(w._handover_due(s, time.time() - 5 * 3600, 0))
        self.assertFalse(w._handover_due(s, time.time(), 3))

    def test_note_then_clear(self):
        inject, sent = self.fake_agent()
        note = w._do_handover(inject, "dev-2", wait=5)
        self.assertEqual(note, "Working on #77. Next: screenshots.")
        self.assertTrue(sent[0].startswith("Scranton: before your next message"))
        self.assertEqual(sent[1], "/clear")

    def test_codex_uses_new(self):
        w._HANDOVER["command"] = "/usr/local/bin/codex"
        inject, sent = self.fake_agent()
        w._do_handover(inject, "dev", wait=5)
        self.assertEqual(sent[-1], "/new")

    def test_no_note_keeps_the_session(self):
        inject, sent = self.fake_agent(write=False)
        self.assertIsNone(w._do_handover(inject, "dev", wait=0.5))
        self.assertNotIn("/clear", sent)

    def test_tool_saves_note(self):
        import mcp_bridge as m
        from unittest.mock import patch
        with patch.object(m, "_HANDOFF_DIR", self.dir), \
                patch.object(m, "_resolve_tool_identity", lambda s, c, **k: (s, None)):
            self.assertIn("saved", m.chat_handoff("qa-2", "All green."))
        self.assertEqual((self.dir / "qa.md").read_text("utf-8"), "All green.")


if __name__ == "__main__":
    unittest.main()
