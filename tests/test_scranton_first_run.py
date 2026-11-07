"""Scranton: first-run answers are recorded without touching anything else."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(home, *args):
    env = {**os.environ, "SCRANTON_HOME": str(home)}
    return subprocess.run([sys.executable, str(ROOT / "tools" / "first_run.py"), *args],
                          capture_output=True, text=True, env=env)


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.folder = os.path.realpath(tempfile.mkdtemp())

    def test_claude_trust_and_full_keep_other_keys(self):
        (self.home / ".claude.json").write_text(json.dumps({"oauthAccount": {"x": 1}, "projects": {"/other": {"a": 1}}}))
        run(self.home, "claude", self.folder, "full")
        state = json.loads((self.home / ".claude.json").read_text())
        self.assertEqual(state["oauthAccount"], {"x": 1})          # login untouched
        self.assertEqual(state["projects"]["/other"], {"a": 1})
        self.assertTrue(state["projects"][self.folder]["hasTrustDialogAccepted"])
        self.assertTrue(state["bypassPermissionsModeAccepted"])
        self.assertTrue(json.loads((self.home / ".claude" / "settings.json").read_text())["skipDangerousModePermissionPrompt"])

    def test_ask_mode_does_not_accept_bypass(self):
        run(self.home, "claude", self.folder, "ask")
        state = json.loads((self.home / ".claude.json").read_text())
        self.assertNotIn("bypassPermissionsModeAccepted", state)
        self.assertFalse((self.home / ".claude" / "settings.json").exists())

    def test_unreadable_claude_state_left_alone(self):
        (self.home / ".claude.json").write_text("{not json")
        r = run(self.home, "claude", self.folder, "full")
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.home / ".claude.json").read_text(), "{not json")

    def test_codex_trust_added_once(self):
        cfg = self.home / ".codex" / "config.toml"
        cfg.parent.mkdir()
        cfg.write_text('model = "gpt-5"\n')
        run(self.home, "codex", self.folder, "full")
        run(self.home, "codex", self.folder, "full")
        text = cfg.read_text()
        self.assertTrue(text.startswith('model = "gpt-5"\n'))
        self.assertEqual(text.count(f'[projects."{self.folder}"]'), 1)
        self.assertIn('trust_level = "trusted"', text)


if __name__ == "__main__":
    unittest.main()
