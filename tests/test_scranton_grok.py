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

    def test_grok_cannot_send_commands(self):
        # /continue, /clear… are Lu's; Grok relays words only.
        import asyncio, json
        from unittest.mock import patch, MagicMock
        import app

        class Req:
            def __init__(self, body): self._b = body
            async def json(self): return self._b

        store = MagicMock()
        with patch.object(app, "room_settings", {"channels": ["general"]}), patch.object(app, "store", store):
            for text in ("/continue", "@pm /continue", "/clear"):
                r = asyncio.run(app.scranton_grok_say(Req({"channel": "general", "text": text})))
                self.assertEqual(r.status_code, 400, text)
            store.add.assert_not_called()
            store.add.return_value = {"id": 5}
            with patch.object(app, "config", {"agents": {}}):
                r = asyncio.run(app.scranton_grok_say(Req({"channel": "general", "text": "see /tmp/x for the log"})))
            self.assertEqual(json.loads(r.body)["id"], 5)

    def test_grok_only_talks_to_the_project_manager(self):
        import asyncio
        from unittest.mock import patch, MagicMock
        import app

        class Req:
            def __init__(self, body): self._b = body
            async def json(self): return self._b

        store = MagicMock(); store.add.return_value = {"id": 9}
        agents = {"pm": {"label": "项目经理"}, "dev": {"label": "开发工程师"}}
        with patch.object(app, "room_settings", {"channels": ["general"]}), patch.object(app, "store", store), \
                patch.object(app, "config", {"agents": agents}):
            for text in ("@dev fix it", "@项目经理 @开发工程师 both of you"):
                r = asyncio.run(app.scranton_grok_say(Req({"channel": "general", "text": text})))
                self.assertEqual(r.status_code, 400, text)
            store.add.assert_not_called()
            for text in ("@项目经理 Lu asks for status", "@pm and @lu"):
                r = asyncio.run(app.scranton_grok_say(Req({"channel": "general", "text": text})))
                self.assertEqual(r.status_code, 200, text)

    def test_line_format(self):
        s = g.line({"id": 7, "channel": "lu-portfolio", "time": "08:42:10", "sender": "pm", "text": "ok", "reply_to": 3}, {"pm": "项目经理"})
        self.assertEqual(s, "[7] #lu-portfolio 08:42 项目经理 ↳3: ok")


if __name__ == "__main__":
    unittest.main()
