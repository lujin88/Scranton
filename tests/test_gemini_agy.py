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

    def test_each_gemini_teammate_gets_its_own_entry_in_agys_config(self):
        with tempfile.TemporaryDirectory() as home:
            glob = Path(home) / ".gemini" / "config" / "mcp_config.json"
            glob.parent.mkdir(parents=True)
            glob.write_text(json.dumps({"mcpServers": {"figma": {"serverUrl": "https://x/mcp"},
                                                       wrapper.SERVER_NAME: {"serverUrl": "old"}}}))
            with mock.patch.dict("os.environ", {"HOME": home}):
                for name, tok in (("visintern", "t1"), ("motionintern", "t2")):
                    inject = wrapper._resolve_mcp_inject(name, {"command": "agy"})
                    wrapper._apply_mcp_inject(inject, name, Path(home) / "data", None,
                                              token=tok, mcp_cfg={"http_port": 8200}, project_dir=Path(home))
            servers = json.loads(glob.read_text())["mcpServers"]
            self.assertEqual(set(servers), {"figma", "scranton-visintern", "scranton-motionintern"})
            self.assertEqual(servers["scranton-visintern"]["headers"], {"Authorization": "Bearer t1"})
            self.assertEqual(servers["scranton-motionintern"]["serverUrl"], "http://127.0.0.1:8200/mcp")

    def test_first_run_trusts_the_worktree(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("first_run", Path(__file__).parent.parent / "tools" / "first_run.py")
        fr = importlib.util.module_from_spec(spec); spec.loader.exec_module(fr)
        with tempfile.TemporaryDirectory() as home:
            st = Path(home) / ".gemini" / "antigravity-cli" / "settings.json"
            st.parent.mkdir(parents=True)
            st.write_text(json.dumps({"colorScheme": "light", "trustedWorkspaces": ["/Users/lu"]}))
            self.assertEqual(fr.agy("/w/visintern", Path(home)), ["agy: folder trusted"])
            self.assertEqual(fr.agy("/w/visintern", Path(home)), [])
            d = json.loads(st.read_text())
            self.assertEqual(d, {"colorScheme": "light", "trustedWorkspaces": ["/Users/lu", "/w/visintern"]})

    def test_a_teammate_cant_act_through_anothers_connection(self):
        import mcp_bridge
        reg = mock.Mock()
        reg.resolve_token.return_value = {"name": "motionintern"}
        reg.get_all_names.return_value = ["visintern", "motionintern", "pm"]
        with mock.patch.object(mcp_bridge, "registry", reg), \
             mock.patch.object(mcp_bridge, "_extract_agent_token", return_value="t2"), \
             mock.patch.object(mcp_bridge, "_touch_presence"):
            name, err = mcp_bridge._resolve_tool_identity("visintern", None, field_name="sender")
            self.assertEqual(name, "")
            self.assertIn("belongs to motionintern", err)
            self.assertEqual(mcp_bridge._resolve_tool_identity("motionintern", None, field_name="sender"), ("motionintern", None))
            self.assertEqual(mcp_bridge._resolve_tool_identity("Motion Intern", None, field_name="sender"), ("motionintern", None))

    def test_only_agys_trust_question_is_answered(self):
        import wrapper_unix
        trust = "Do you trust the contents of this project?\n\n> Yes, I trust this folder\n  No, exit\n"
        other = "Run rm -rf build?\nDo you want to proceed?\n> Yes\n  No\n"
        no_selected = "Do you trust the contents of this project?\n\n  Yes, I trust this folder\n> No, exit\n"
        for screen, expect in ((trust, True), (other, False), (no_selected, False)):
            sent = []
            with mock.patch.object(wrapper_unix, "pane_text", return_value=screen), \
                 mock.patch.object(wrapper_unix.subprocess, "run", side_effect=lambda *a, **k: sent.append(a)), \
                 mock.patch.object(wrapper_unix, "waiting_on_question", return_value=False):
                wrapper_unix._answer_agy_trust("agentchattr-x")
            self.assertEqual(bool(sent), expect, screen)


if __name__ == "__main__":
    unittest.main()
