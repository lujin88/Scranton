"""After a restart, Lu's queued messages are never dropped (Lu, 11-10)."""
import json
import tempfile
import unittest
from pathlib import Path

import wrapper


class KeepLu(unittest.TestCase):
    def test_lus_messages_survive_the_trim(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "settings.json").write_text(json.dumps({"username": "Lu"}))
            q = d / "pm_queue.jsonl"
            rows = [{"sender": "Lu", "text": "Lu: @pm 在么？"}] + [{"sender": f"dev{i}", "text": f"dev{i}: x"} for i in range(8)] \
                + [{"sender": "Lu", "text": "Lu: @pm 请继续"}]
            q.write_text("".join(json.dumps(r) + "\n" for r in rows))
            taking = d / "pm_queue.jsonl.taking"
            dropped = wrapper._take_queue(q, taking, keep=3)
            kept = [json.loads(l)["sender"] for l in taking.read_text().splitlines()]
            self.assertEqual(kept, ["Lu", "dev5", "dev6", "dev7", "Lu"])
            self.assertEqual(dropped, 5)


if __name__ == "__main__":
    unittest.main()
