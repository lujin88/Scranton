"""Scranton: daily schedules from config, per-teammate git identity, worktree folders."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
from schedules import ScheduleStore

ROOT = Path(__file__).resolve().parent.parent
CFG_SCHED = {"id": "daily-backup", "daily_at": "21:00", "to": ["pm"], "channel": "lu-portfolio", "text": "backup"}


class TeamScheduleSeedTests(unittest.TestCase):
    def run_seed(self, tmp, settings):
        cfg = {"server": {"data_dir": str(tmp)}, "team": {"schedules": [CFG_SCHED]}}
        store = ScheduleStore(str(tmp / "schedules.json"))
        with mock.patch.object(app, "config", cfg), mock.patch.object(app, "room_settings", settings), \
             mock.patch.object(app, "schedules", store):
            app._seed_team_schedules(cfg)
            return store, dict(app.room_settings)

    def test_created_once_and_posted_by_scranton(self):
        tmp = Path(tempfile.mkdtemp())
        store, settings = self.run_seed(tmp, {"title": "Scranton"})
        rows = store.list_all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["targets"], ["pm"])
        self.assertEqual(rows[0]["created_by"], "Scranton")
        # restart: already seeded, so nothing new even though Lu deleted it
        store.delete(rows[0]["id"])
        store2, _ = self.run_seed(tmp, dict(settings))
        self.assertEqual(store2.list_all(), [])

    def test_bad_entries_ignored(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = {"team": {"schedules": [{"id": "x", "daily_at": "9pm", "to": ["pm"], "text": "t"},
                                        {"id": "y", "daily_at": "21:00", "to": [], "text": "t"}]}}
        store = ScheduleStore(str(tmp / "s.json"))
        with mock.patch.object(app, "room_settings", {}), mock.patch.object(app, "schedules", store), \
             mock.patch.object(app, "config", {"server": {"data_dir": str(tmp)}}):
            app._seed_team_schedules(cfg)
        self.assertEqual(store.list_all(), [])


class GitIdentityTests(unittest.TestCase):
    def test_git_config_env_is_what_git_config_reports(self):
        """The harness check runs `git config user.email`; GIT_CONFIG_* must answer it."""
        repo = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        env = {**os.environ, "GIT_CONFIG_COUNT": "2",
               "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "开发工程师 (Scranton dev)",
               "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "bot@example.com"}
        out = subprocess.run(["git", "-C", str(repo), "config", "user.email"], env=env, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "bot@example.com")

    def test_wrapper_sets_identity_from_team_email(self):
        src = (ROOT / "wrapper.py").read_text("utf-8")
        self.assertIn('"GIT_CONFIG_KEY_1": "user.email"', src)
        self.assertIn('config.get("team", {}).get("git_email"', src)


class WorktreeConfigTests(unittest.TestCase):
    def test_code_changing_roles_get_worktrees(self):
        import tomllib
        cfg = tomllib.loads((ROOT / "config.toml").read_text("utf-8"))
        wt = {n for n, a in cfg["agents"].items() if a.get("worktree")}
        self.assertTrue({"dev", "qa", "visual", "motion"} <= wt)
        self.assertNotIn("pm", wt)

    def test_wrapper_uses_scranton_cwd(self):
        src = (ROOT / "wrapper.py").read_text("utf-8")
        self.assertIn('os.environ.get("SCRANTON_CWD")', src)


if __name__ == "__main__":
    unittest.main()


class TeamPermissionsTest(unittest.TestCase):
    def test_first_launch_choice_is_saved_and_applied(self):
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch
        import scranton_team as t
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "teammates.json"
            with patch.object(t, "OVERRIDES", p):
                self.assertEqual(t.team_permissions("full"), {"permissions": "full", "asked": False})
                self.assertEqual(t.set_team_permissions("ask"), {"permissions": "ask", "asked": True})
                self.assertEqual(json.loads(p.read_text())["_team"]["permissions"], "ask")
                with self.assertRaises(ValueError):
                    t.set_team_permissions("root")
