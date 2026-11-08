"""A decision card's "Something else" row: a typed answer resolves the card (Lu, 2026-11-08)."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from store import MessageStore


def _post(msg_id, body):
    request = Mock()
    async def j(): return body
    request.json = j
    return asyncio.run(app.resolve_decision(msg_id, request))


class DecisionOther(unittest.TestCase):
    def test_typed_answer_resolves_and_options_still_checked(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(app, 'store', MessageStore(str(Path(d) / 'm.jsonl'))) as store, \
                patch.object(app, 'room_settings', {'username': 'Lu'}), \
                patch.object(app, 'ws_clients', set()):
            q = store.add('pm', 'Ship it?', msg_type='decision', metadata={'choices': ['Yes', 'No'], 'resolved': False})
            bad = _post(q['id'], {'choice': 'Maybe'})
            self.assertEqual(bad.status_code, 400)          # not an option, not typed: refused
            ok = _post(q['id'], {'choice': '  smaller title  ', 'other': True})
            self.assertEqual(ok['chosen'], 'smaller title')
            meta = store.get_by_id(q['id'])['metadata']
            self.assertTrue(meta['resolved'] and meta['other'])
            self.assertIn('@pm C：smaller title', [m['text'] for m in store.get_recent(10)])


if __name__ == '__main__':
    unittest.main()
