"""Scranton: channel members — seeded from config once, kept across restarts, follow renames."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
import scranton_ops as ops

AGENTS = {"pm": {"command": "claude"}, "dev": {"command": "claude"}, "help": {"command": "claude"}}


def cfg(tmp, members):
    return {"server": {"data_dir": str(tmp)}, "agents": AGENTS,
            "team": {"channels": ["lu-portfolio"], "members": members}}


class MemberSeedTests(unittest.TestCase):
    def load(self, c, settings=None):
        with mock.patch.object(app, "config", c), \
             mock.patch.object(app, "room_settings", settings or {"title": "Scranton", "username": "user"}):
            app._load_settings()
            return json.loads(json.dumps(app.room_settings))

    def test_seeded_from_config_unknown_names_dropped(self):
        tmp = Path(tempfile.mkdtemp())
        s = self.load(cfg(tmp, {"lu-portfolio": ["pm", "dev", "nobody"]}))
        self.assertEqual(s["channel_members"]["lu-portfolio"], ["pm", "dev"])

    def test_lu_removal_survives_restart(self):
        tmp = Path(tempfile.mkdtemp())
        c = cfg(tmp, {"lu-portfolio": ["pm", "dev"]})
        s = self.load(c)
        s["channel_members"]["lu-portfolio"] = ["pm"]          # Lu removed dev
        (tmp / "settings.json").write_text(json.dumps(s), "utf-8")
        s2 = self.load(c)
        self.assertEqual(s2["channel_members"]["lu-portfolio"], ["pm"])

    def test_add_members_only_known_and_not_dm(self):
        tmp = Path(tempfile.mkdtemp())
        rs = {"channels": ["general", "lu-portfolio", "dm-pm"], "channel_members": {"lu-portfolio": ["pm"]}}
        with mock.patch.object(app, "config", cfg(tmp, {})), mock.patch.object(app, "room_settings", rs):
            self.assertEqual(app._add_members("lu-portfolio", ["dev", "pm", "evil"]), ["dev"])
            self.assertEqual(app._add_members("dm-pm", ["dev"]), [])
            self.assertEqual(app._add_members("missing", ["dev"]), [])
            self.assertEqual(rs["channel_members"]["lu-portfolio"], ["pm", "dev"])


class EnsureRunningTests(unittest.TestCase):
    def setUp(self):
        self.run = Path(tempfile.mkdtemp())
        p = mock.patch.object(ops, "RUN_DIR", self.run); p.start(); self.addCleanup(p.stop)

    def test_missing_cli_and_folder_reported(self):
        c = {"agents": {"a": {"command": "definitely-not-a-cli"},
                        "b": {"command": "sh", "cwd": "/no/such/folder"}}}
        with mock.patch.object(ops.subprocess, "Popen") as popen:
            r = ops.ensure_running(["a", "b"], c)
        popen.assert_not_called()
        self.assertIn("isn't installed", r["failed"]["a"])
        self.assertIn("doesn't exist", r["failed"]["b"])

    def test_starts_once_and_skips_running(self):
        c = {"agents": {"a": {"command": "sh", "cwd": "/"}, "b": {"command": "sh", "cwd": "/"}}}
        (self.run / "b.pid").write_text("12345")
        with mock.patch.object(ops, "_alive", lambda pid: pid == 12345), \
             mock.patch.object(ops.subprocess, "Popen") as popen:
            r = ops.ensure_running(["a", "a", "b", "unknown"], c)
        self.assertEqual(r["started"], ["a"])
        self.assertEqual(r["running"], ["b"])
        self.assertEqual(popen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
