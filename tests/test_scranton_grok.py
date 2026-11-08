import tempfile, unittest
from pathlib import Path

import scranton_grok as g
from router import Router


class GrokTest(unittest.TestCase):
    def test_token_is_made_once_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            g.setup(d)
            t = g.token()
            self.assertGreaterEqual(len(t), 32)
            self.assertEqual(g.token(), t)
            self.assertEqual(oct((Path(d) / "grok-token").stat().st_mode & 0o777), "0o600")
            self.assertTrue(g.check(t))
            self.assertFalse(g.check("") or g.check(t + "x"))

    def test_grok_without_mention_reaches_nobody(self):
        r = Router(["pm", "dev"], default_mention="both")
        self.assertEqual(r.get_targets("grok", "hello team", "lu-portfolio"), [])
        self.assertEqual(r.get_targets("grok", "@pm status please", "lu-portfolio"), ["pm"])

    def test_line_format(self):
        s = g.line({"id": 7, "channel": "lu-portfolio", "time": "08:42:10", "sender": "pm", "text": "ok", "reply_to": 3}, {"pm": "项目经理"})
        self.assertEqual(s, "[7] #lu-portfolio 08:42 项目经理 ↳3: ok")


if __name__ == "__main__":
    unittest.main()
