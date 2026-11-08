import os, tempfile, unittest
from pathlib import Path

from store import MessageStore


class StoreUpdateTest(unittest.TestCase):
    def test_update_is_appended_then_folded_in_on_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log.jsonl"
            s = MessageStore(str(p))
            m = s.add("Lu", "hi")
            s.add("pm", "hello")
            size = p.stat().st_size
            s.update_message(m["id"], {"reactions": {"👍": ["Lu"]}})
            self.assertGreater(p.stat().st_size, size)            # appended, not rewritten
            self.assertIn('"_update"', p.read_text())
            s2 = MessageStore(str(p))
            self.assertEqual(s2.get_by_id(m["id"])["reactions"], {"👍": ["Lu"]})
            self.assertEqual(len(s2.get_since(-1)), 2)            # the update line isn't a message
            self.assertNotIn('"_update"', p.read_text())           # compacted on load


if __name__ == "__main__":
    unittest.main()
