"""Gemini via Antigravity CLI (agy) as a teammate's app (Lu, 11-10)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scranton_team
import wrapper


class GeminiProvider(unittest.TestCase):
    def test_agy_is_gemini(self):
        self.assertEqual(scranton_team.provider_of("agy"), "gemini")
        self.assertEqual(scranton_team.provider_of("/Users/lu/.local/bin/agy"), "gemini")
        self.assertEqual(scranton_team.COMMANDS["gemini"], "agy")
        self.assertIn("gemini-4-argon", [m[0] for m in scranton_team.PROVIDERS["gemini"]["models"]])
        self.assertEqual(scranton_team.EFFORTS_BY["gemini"], ("low", "medium", "high"))

    def test_mcp_goes_to_the_teammates_own_workspace(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as wt:
            glob = Path(home) / ".gemini" / "config" / "mcp_config.json"
            glob.parent.mkdir(parents=True)
            # an older Scranton put its entry here; Lu's own servers must stay
            glob.write_text(json.dumps({"mcpServers": {"figma": {"serverUrl": "https://x/mcp"},
                                                       wrapper.SERVER_NAME: {"serverUrl": "old"}}}))
            inject = wrapper._resolve_mcp_inject("visintern", {"command": "agy"})
            with mock.patch.dict("os.environ", {"HOME": home}):
                wrapper._apply_mcp_inject(inject, "visintern", Path(home) / "data", None,
                                          token="t0k", mcp_cfg={"http_port": 8200}, project_dir=Path(wt))
            self.assertEqual(json.loads(glob.read_text())["mcpServers"], {"figma": {"serverUrl": "https://x/mcp"}})
            ours = json.loads((Path(wt) / ".agents" / "mcp_config.json").read_text())["mcpServers"][wrapper.SERVER_NAME]
            self.assertEqual(ours["serverUrl"], "http://127.0.0.1:8200/mcp")
            self.assertEqual(ours["headers"], {"Authorization": "Bearer t0k"})

if __name__ == "__main__":
    unittest.main()
