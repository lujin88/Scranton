import unittest
from unittest import mock

import wrapper
import wrapper_unix as wu

BRIEF = ("Plan limits: if your app says you've hit a usage limit, stop, say so once in the channel "
         "with @Lu, and don't retry until she answers.")


class ProblemDetectionTest(unittest.TestCase):
    def screen(self, text, injected=""):
        wu._LAST_INJECTED["s"] = wu._norm(injected)
        with mock.patch.object(wu, "pane_text", return_value=text), \
             mock.patch.object(wu, "waiting_on_question", return_value=False):
            return wu.describe_screen("s")[1]

    def test_echo_of_our_prompt_is_not_a_limit(self):
        self.assertIsNone(self.screen("> " + BRIEF + "\n", injected=BRIEF))

    def test_real_limit_banner_counts(self):
        self.assertEqual(self.screen("⏺ Done reading\n  ⎿ You've hit your limit · resets 3pm\n", injected=BRIEF), "limit")

    def test_spinner_means_still_working(self):
        self.assertIsNone(self.screen("  ⎿ rate limit in the docs\n✻ Thinking… (esc to interrupt)\n"))

    def test_codex_switch_model_nudge_is_a_question_not_a_limit(self):
        nudge = ("  Approaching rate limits\n  Switch to gpt-6.1-sol for lower credit usage?\n"
                 "› 1. Switch to gpt-6.1-sol  Uses fewer credits for upcoming turns\n"
                 "  2. Keep current model\n  3. Keep current model (never show again)\n"
                 "     Hide future rate limit reminders about switching models\n"
                 "  Press enter to confirm or esc to go back\n")
        self.assertEqual(self.screen(nudge), "question")
        self.assertTrue(wu._QUESTION_RE.search(nudge))   # so nothing is typed into it

    def test_codex_real_usage_limit_still_counts(self):
        self.assertEqual(self.screen("■ You've hit your usage limit. Try again at 8:32 AM.\n"), "limit")

    def test_codex_launch_hides_switch_model_nudge(self):
        self.assertEqual(wrapper._CODEX_ARGS, ["-c", "notice.hide_rate_limit_model_nudge=true"])
        self.assertEqual(wrapper._provider_from_command("codex"), "codex")

    def test_question_when_waiting(self):
        wu._LAST_INJECTED["s"] = ""
        with mock.patch.object(wu, "pane_text", return_value="Do you want to proceed?\n❯ 1. Yes\n"), \
             mock.patch.object(wu, "waiting_on_question", return_value=True):
            self.assertEqual(wu.describe_screen("s")[1], "question")

    def test_auto_posts_dont_count_as_reply(self):
        msgs = [{"sender": "pm", "timestamp": 10, "text": "I stopped: my terminal is waiting on a question."},
                {"sender": "dev", "timestamp": 11, "text": "done"}]
        self.assertFalse(wrapper._replied_since(msgs, "pm", 5))
        msgs.append({"sender": "pm-2", "timestamp": 12, "text": "Here is the plan"})
        self.assertTrue(wrapper._replied_since(msgs, "pm", 5))


if __name__ == "__main__":
    unittest.main()
