"""Scranton: sub-agents are handed to one teammate at launch, nothing written to ~/.claude or ~/.codex."""
import json
import unittest

import wrapper


class SubagentArgsTests(unittest.TestCase):
    def test_claude_gets_agents_json(self):
        a = wrapper._subagent_args({"subagents": "roles/subagents/qa.json"}, "claude")
        self.assertEqual(a[0], "--agents")
        d = json.loads(a[1])
        self.assertEqual(d["test-runner"]["model"], "haiku")
        self.assertNotIn("Edit", d["test-runner"]["tools"])

    def test_codex_gets_config_overrides(self):
        a = wrapper._subagent_args({"subagents": ["roles/subagents/visualqa-shots.toml"]}, "codex")
        self.assertEqual(a[0], "-c")
        self.assertTrue(a[1].startswith("agents.shot_checker.description="))
        self.assertTrue(a[3].startswith("agents.shot_checker.config_file=") and a[3].endswith('visualqa-shots.toml"'))

    def test_wrong_app_missing_file_or_outside_roles_ignored(self):
        self.assertEqual(wrapper._subagent_args({"subagents": "roles/subagents/qa.json"}, "codex"), [])
        self.assertEqual(wrapper._subagent_args({"subagents": "roles/subagents/nope.json"}, "claude"), [])
        self.assertEqual(wrapper._subagent_args({"subagents": "../../etc/passwd"}, "claude"), [])
        self.assertEqual(wrapper._subagent_args({}, "claude"), [])


if __name__ == "__main__":
    unittest.main()
