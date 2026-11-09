"""Scranton Report: a PR shows its GitHub title (same request as the merged check), the chat line only as fallback."""
import time
import unittest
from unittest import mock

import scranton_report as rep


def msgs(n):
    now = time.time()
    return [{"id": i, "sender": "dev", "type": "chat", "channel": "general", "timestamp": now - 60 * i,
             "text": f"PR ready https://github.com/lujin88/Scranton/pull/{100 + i} please merge"} for i in range(n)]


class PrTitleTests(unittest.TestCase):
    def build(self, info):
        with mock.patch.object(rep, "pr_info", info), mock.patch.object(rep, "_gh_blocked", [0.0]):
            return rep.build(msgs(3), {"dev": {}}, "lu")

    def test_github_title_wins(self):
        r = self.build(lambda u: {"merged": u.endswith("/100"), "title": "Fix hero spacing #" + u[-3:]})
        titles = {p["url"][-3:]: p["title"] for p in r["shipped"]}
        self.assertEqual(titles["101"], "Fix hero spacing #101")
        self.assertTrue(next(p for p in r["shipped"] if p["url"].endswith("/100"))["merged"])

    def test_chat_line_when_github_unreachable(self):
        r = self.build(lambda u: None)
        self.assertTrue(all(p["title"].startswith("PR ready") for p in r["shipped"]))
        self.assertTrue(all(p["checked"] is False for p in r["shipped"]))


if __name__ == "__main__":
    unittest.main()
