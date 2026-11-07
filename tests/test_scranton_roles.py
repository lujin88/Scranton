"""Scranton: role and team brief from config.toml reach the agent's wake-up prompt."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wrapper


class _Stop(Exception):
    pass


def run_watcher(triggers, *, ui_role="", default_role="", team_brief="", refresh_interval=10):
    """Feed `triggers` wake-ups through the watcher, return the injected prompts."""
    tmp = Path(tempfile.mkdtemp())
    queue = tmp / "queue.jsonl"
    injected = []
    remaining = [triggers]

    def fake_sleep(seconds):
        if seconds == 1:  # end of a loop pass
            if remaining[0] == 0:
                raise _Stop
            queue.write_text(json.dumps({"channel": "lu-portfolio"}) + "\n", "utf-8")
            remaining[0] -= 1

    with (
        mock.patch.object(wrapper.time, "sleep", side_effect=fake_sleep),
        mock.patch.object(wrapper, "_fetch_role", return_value=ui_role),
        mock.patch.object(wrapper, "_fetch_active_rules", return_value=None),
    ):
        try:
            wrapper._queue_watcher(
                lambda: ("pm", queue), injected.append,
                agent_name="pm", default_role=default_role, team_brief=team_brief,
                refresh_interval=refresh_interval,
            )
        except _Stop:
            pass
    return injected


class ScrantonRoleTests(unittest.TestCase):
    def test_config_role_used_when_ui_role_empty(self):
        prompts = run_watcher(1, default_role="项目经理：项目统筹")
        self.assertEqual(len(prompts), 1)
        self.assertIn("lu-portfolio", prompts[0])
        self.assertIn("ROLE: 项目经理：项目统筹", prompts[0])

    def test_ui_role_is_added_to_config_role(self):
        prompts = run_watcher(1, ui_role="Reviewer", default_role="项目经理 | 角色卡: /x/roles/pm.md")
        self.assertIn("ROLE: Reviewer | 项目经理 | 角色卡: /x/roles/pm.md", prompts[0])

    def test_team_brief_on_first_wake_and_every_refresh(self):
        prompts = run_watcher(5, team_brief="称呼 Lu，用简洁中文。", refresh_interval=3)
        with_brief = [i for i, p in enumerate(prompts) if "TEAM: 称呼 Lu" in p]
        self.assertEqual(with_brief, [0, 3])

    def test_prompt_is_single_line(self):
        prompts = run_watcher(1, default_role="x", team_brief="y")
        self.assertNotIn("\n", prompts[0])


if __name__ == "__main__":
    unittest.main()


class ScrantonChannelSeedTests(unittest.TestCase):
    def test_team_channels_created_and_ui_channels_kept(self):
        import app
        tmp = Path(tempfile.mkdtemp())
        (tmp / "settings.json").write_text(json.dumps({"channels": ["general", "mine"]}), "utf-8")
        with (
            mock.patch.object(app, "config", {"server": {"data_dir": str(tmp)},
                                              "team": {"channels": ["lu-portfolio", "Bad Name!"]}}),
            mock.patch.object(app, "room_settings", dict(app.room_settings)),
        ):
            app._load_settings()
            self.assertEqual(app.room_settings["channels"], ["general", "mine", "lu-portfolio"])


class ScrantonDmRoutingTests(unittest.TestCase):
    def make(self):
        from router import Router
        return Router(["pm", "dev", "visual", "visualqa"], default_mention="none")

    def test_plain_message_in_dm_goes_to_that_teammate(self):
        self.assertEqual(self.make().get_targets("Lu", "你好", "dm-pm"), ["pm"])

    def test_dm_handle_is_exact(self):
        self.assertEqual(self.make().get_targets("Lu", "hi", "dm-visual"), ["visual"])

    def test_explicit_mention_in_dm_still_wins(self):
        self.assertEqual(sorted(self.make().get_targets("Lu", "@dev look", "dm-pm")), ["dev"])

    def test_plain_message_in_normal_channel_goes_nowhere(self):
        self.assertEqual(self.make().get_targets("Lu", "hello", "lu-portfolio"), [])

    def test_agent_message_in_dm_does_not_loop(self):
        r = self.make()
        self.assertEqual(r.get_targets("pm", "done", "dm-pm"), [])
