"""Scranton: editing a message to @ someone new offers to send it to them; nothing is sent without asking."""
import unittest
from unittest import mock

import app
from router import Router

AGENTS = {"pm": {"command": "claude"}, "dev": {"command": "claude"}, "qa": {"command": "codex"}}


class EditMentionTests(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch.object(app, "config", {"agents": AGENTS}),
                  mock.patch.object(app, "router", Router(list(AGENTS) + ["grok"]))]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_only_newly_added_teammates(self):
        self.assertEqual(app._added_mentions("@pm fix the hero", "@pm @qa fix the hero"), ["qa"])
        self.assertEqual(app._added_mentions("@pm fix it", "@pm fix it now"), [])
        self.assertEqual(app._added_mentions("@pm", "@dev"), ["dev"])   # removed pm: nothing to un-send

    def test_strangers_and_grok_are_not_offered(self):
        self.assertEqual(app._added_mentions("hi", "hi @nobody @grok"), [])

    def test_only_your_own_chat_messages(self):
        self.assertTrue(app._is_humans_chat({"sender": "lu", "type": "chat", "text": "x"}))
        for m in ({"sender": "pm", "type": "chat"}, {"sender": "pm-2", "type": "chat"},
                  {"sender": "system", "type": "chat"}, {"sender": "grok", "type": "chat"},
                  {"sender": "lu", "type": "decision"}, None):
            self.assertFalse(app._is_humans_chat(m))


if __name__ == "__main__":
    unittest.main()
