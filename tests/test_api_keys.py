"""Backup API keys: used only while a teammate's plan is out (Lu, 11-10)."""
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import scranton_apikeys as k

KEY_A = "sk-ant-api03-" + "a" * 40
KEY_O = "sk-proj-" + "b" * 40


class Keys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p = [mock.patch.object(k, "KEYS_DIR", d / "keys"), mock.patch.object(k, "MODE_FILE", d / "api-mode.json")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_saved_private_never_returned(self):
        self.assertEqual(k.set_key("claude", KEY_A), "")
        f = k.KEYS_DIR / "anthropic"
        self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(k.KEYS_DIR).st_mode), 0o700)
        s = k.summary()
        self.assertEqual(s["claude"], {"set": True, "last4": "aaaa", "limits_url": k.PROVIDERS["claude"][3]})
        self.assertNotIn(KEY_A, json.dumps(s))
        self.assertFalse(s["codex"]["set"])

    def test_rejects_wrong_kind_of_key(self):
        self.assertIn("Anthropic", k.set_key("claude", KEY_O))
        self.assertIn("OpenAI", k.set_key("codex", "hello"))
        self.assertEqual(k.set_key("cursor", KEY_O), "unknown app")

    def test_remove(self):
        k.set_key("codex", KEY_O)
        k.set_key("codex", "")
        self.assertEqual(k.get_key("codex"), "")

    def test_only_teammates_on_the_api_get_the_key(self):
        cmd = "claude --model opus"
        self.assertEqual(k.wrap_command("dev", "dev", cmd), cmd)          # not on the API
        self.assertFalse(k.start_api("dev", "claude"))                     # no key yet
        k.set_key("claude", KEY_A)
        self.assertTrue(k.start_api("dev", "claude"))
        wrapped = k.wrap_command("dev", "dev", "printenv ANTHROPIC_API_KEY")
        self.assertNotIn(KEY_A, wrapped)                                   # never on the command line
        out = subprocess.run(wrapped, shell=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, KEY_A)
        self.assertEqual(k.wrap_command("pm", "pm", cmd), cmd)

    def test_back_to_plan_after_five_hours(self):
        k.set_key("codex", KEY_O)
        k.start_api("visual", "codex")
        self.assertEqual(k.due_back(), [])
        self.assertEqual(k.due_back(time.time() + k.TRY_PLAN_AFTER + 1), ["visual"])
        self.assertTrue(k.end_api("visual"))
        self.assertIsNone(k.on_api("visual"))

    def test_claude_approval_recorded_like_claude_code(self):
        k.set_key("claude", KEY_A)
        with tempfile.TemporaryDirectory() as home:
            cj = Path(home) / ".claude.json"
            cj.write_text(json.dumps({"numStartups": 3, "customApiKeyResponses": {"approved": [], "rejected": [KEY_A[-20:]]}}))
            k.approve_for_claude(Path(home))
            d = json.loads(cj.read_text())
            self.assertEqual(d["numStartups"], 3)
            self.assertEqual(d["customApiKeyResponses"], {"approved": [KEY_A[-20:]], "rejected": []})


if __name__ == "__main__":
    unittest.main()
