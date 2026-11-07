"""Scranton: per-Mac settings live in config.local.toml so config.toml stays clean for updates."""
import tempfile
import unittest
from pathlib import Path

from config_loader import load_config

BASE = '''
[server]
port = 8300
allowed_origins = []
[team]
owner = "Lu"
permissions = "full"
[agents.pm]
command = "claude"
cwd = "../LuJin-Portfolio"
[agents.growth]
command = "claude"
autostart = false
'''


class LocalConfigTests(unittest.TestCase):
    def load(self, local):
        d = Path(tempfile.mkdtemp())
        (d / "config.toml").write_text(BASE)
        (d / "config.local.toml").write_text(local)
        return load_config(d)

    def test_phone_origin_from_local(self):
        c = self.load('[server]\nallowed_origins = ["https://mac.tail1.ts.net"]\n')
        self.assertEqual(c["server"]["allowed_origins"], ["https://mac.tail1.ts.net"])

    def test_teammate_tweaks_allowed(self):
        c = self.load('[agents.growth]\nautostart = true\n[agents.pm]\npermissions = "ask"\n')
        self.assertTrue(c["agents"]["growth"]["autostart"])
        self.assertEqual(c["agents"]["pm"]["permissions"], "ask")

    def test_command_cannot_be_swapped_locally(self):
        c = self.load('[agents.pm]\ncommand = "rm"\n')
        self.assertEqual(c["agents"]["pm"]["command"], "claude")

    def test_team_settings(self):
        c = self.load('[team]\npermissions = "ask"\n')
        self.assertEqual(c["team"]["permissions"], "ask")
        self.assertEqual(c["team"]["owner"], "Lu")


if __name__ == "__main__":
    unittest.main()
