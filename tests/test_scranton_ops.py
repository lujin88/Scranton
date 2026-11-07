"""Scranton: update check/apply against a real local git origin, and resume of stopped teammates."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scranton_ops as ops


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.dev = self.tmp / "dev"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.dev)], check=True)
        for repo in (self.dev,):
            git(repo, "config", "user.email", "t@example.com"); git(repo, "config", "user.name", "t")
        (self.dev / "a.txt").write_text("1")
        git(self.dev, "add", "."); git(self.dev, "commit", "-qm", "first"); git(self.dev, "push", "-q", "origin", "main")
        self.mine = self.tmp / "mine"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.mine)], check=True)
        self.p = mock.patch.object(ops, "ROOT", self.mine)
        self.p.start()
        self.addCleanup(self.p.stop)
        ops._state.update(behind=0, subject="", error="", updating=False)

    def push_change(self, subject):
        (self.dev / "a.txt").write_text(subject)
        git(self.dev, "commit", "-qam", subject); git(self.dev, "push", "-q", "origin", "main")

    def test_up_to_date(self):
        self.assertEqual(ops.check_update()["behind"], 0)

    def test_detects_new_commits(self):
        self.push_change("Add Activity view")
        st = ops.check_update()
        self.assertEqual(st["behind"], 1)
        self.assertEqual(st["subject"], "Add Activity view")

    def test_apply_fast_forwards_and_restarts(self):
        self.push_change("v2")
        ops.check_update()
        with mock.patch.object(ops, "_restart_server_soon") as restart:
            r = ops.apply_update()
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.mine / "a.txt").read_text(), "v2")
        restart.assert_called_once()

    def test_apply_refuses_with_local_changes(self):
        self.push_change("v2")
        (self.mine / "a.txt").write_text("my local edit")
        with mock.patch.object(ops, "_restart_server_soon") as restart:
            r = ops.apply_update()
        self.assertFalse(r["ok"])
        self.assertIn("local changes", r["error"])
        restart.assert_not_called()

    def test_offline_is_an_error_not_a_crash(self):
        git(self.mine, "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        st = ops.check_update()
        self.assertTrue(st["error"])


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.run = Path(tempfile.mkdtemp())
        self.p = mock.patch.object(ops, "RUN_DIR", self.run)
        self.p.start()
        self.addCleanup(self.p.stop)
        self.cfg = {"agents": {"pm": {}, "dev": {}, "qa": {}}}

    def test_only_dead_teammates_listed(self):
        (self.run / "pm.pid").write_text("999999")            # dead
        (self.run / "dev.pid").write_text(str(os.getpid()))   # alive
        (self.run / "server.pid").write_text("999998")        # server isn't a teammate
        (self.run / "ghost.pid").write_text("999997")         # not in config
        with mock.patch.object(ops, "_alive", lambda pid: pid == os.getpid()):
            self.assertEqual(ops.stopped_agents(self.cfg), ["pm"])

    def test_reused_pid_is_not_ours(self):
        # After a reboot an unrelated process can own the old pid: that teammate is stopped.
        self.assertFalse(ops._alive(os.getpid()))   # this test runner isn't wrapper.py

    def test_resume_never_duplicates_a_running_teammate(self):
        (self.run / "dev.pid").write_text(str(os.getpid()))
        with mock.patch.object(ops, "_alive", lambda pid: True), \
             mock.patch.object(ops.subprocess, "Popen") as popen:
            r = ops.resume(["dev"], self.cfg)
        self.assertEqual(r["started"], [])
        popen.assert_not_called()
        self.assertTrue((self.run / "dev.pid").exists())

    def test_dismiss_forgets(self):
        (self.run / "pm.pid").write_text("999999")
        ops.dismiss(["pm", "../etc"])
        self.assertEqual(ops.stopped_agents(self.cfg), [])

    def test_resume_starts_only_known_names(self):
        (self.run / "pm.pid").write_text("999999")
        with mock.patch.object(ops.subprocess, "Popen") as popen:
            r = ops.resume(["pm", "rm -rf", "nobody"], self.cfg)
        self.assertEqual(r["started"], ["pm"])
        args = popen.call_args[0][0]
        self.assertEqual(args[1:], ["start-agent", "pm"])
        self.assertFalse((self.run / "pm.pid").exists())


if __name__ == "__main__":
    unittest.main()
