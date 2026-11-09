"""chat_read and the other chat tools answer with plain text, not a {"result": "..."} wrapper
(that wrapper made Claude Code show the messages escaped twice)."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_bridge


class PlainText(unittest.TestCase):
    def test_no_structured_output(self):
        tools = asyncio.run(mcp_bridge.mcp_http.list_tools())
        self.assertTrue(tools)
        self.assertEqual([t.name for t in tools if t.outputSchema], [])


if __name__ == '__main__':
    unittest.main()
