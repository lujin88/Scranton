"""Scranton: only the project manager @s Lu; a teammate's @Lu goes to the PM (Lu, 11-10)."""
import unittest
from unittest import mock

import app

AGENTS = {"pm": {"command": "claude"}, "dev": {"command": "claude"}, "qa": {"command": "codex"}}


class OnlyPmMentionsLu(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch.object(app, "config", {"agents": AGENTS, "team": {"mentions_from": "pm"}}),
                  mock.patch.dict(app.room_settings, {"username": "Lu"})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_teammate_opening_with_lu_goes_to_pm(self):
        self.assertTrue(app._lu_ask_for_pm("dev", "@Lu 选 A 还是 B？", "lu-portfolio"))
        self.assertTrue(app._lu_ask_for_pm("qa-2", "@qa @lu PR 要你合", "general"))

    def test_not_redirected(self):
        self.assertFalse(app._lu_ask_for_pm("pm", "@Lu 两件事要你定", "general"))      # the PM may
        self.assertFalse(app._lu_ask_for_pm("dev", "做完了，Lu 说的那条也改了", "general"))  # no @
        self.assertFalse(app._lu_ask_for_pm("dev", "改好了，回头给 @Lu 看", "general"))  # not at the start
        self.assertFalse(app._lu_ask_for_pm("dev", "@Lu 好了", "dm-dev"))              # her DM
        self.assertFalse(app._lu_ask_for_pm("Lu", "@Lu test", "general"))
        self.assertFalse(app._lu_ask_for_pm("system", "@Lu x", "general"))
        self.assertFalse(app._lu_ask_for_pm("dev", "@Lucas hi", "general"))


    def test_off_when_not_set(self):
        with mock.patch.object(app, "config", {"agents": AGENTS, "team": {}}):
            self.assertFalse(app._lu_ask_for_pm("dev", "@Lu 选 A 还是 B？", "general"))


if __name__ == "__main__":
    unittest.main()
