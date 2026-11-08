"""Scrolling up asks for messages older than the oldest one the page has."""
import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

import app


class OlderTest(unittest.TestCase):
    def test_older_pages_by_channel(self):
        msgs = [{"id": i, "channel": "a" if i % 2 else "b", "text": str(i)} for i in range(300)]
        store = MagicMock()
        store.get_since.return_value = msgs
        with patch.object(app, "store", store):
            r = json.loads(asyncio.run(app.scranton_older(channel="a", before=101, limit=10)).body)
            self.assertEqual([m["id"] for m in r["messages"]], list(range(81, 101, 2)))
            self.assertTrue(r["more"])
            r = json.loads(asyncio.run(app.scranton_older(channel="a", before=5)).body)
            self.assertEqual([m["id"] for m in r["messages"]], [1, 3])
            self.assertFalse(r["more"])


if __name__ == "__main__":
    unittest.main()
