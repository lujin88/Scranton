"""Settings → paste a picture link: never fetch this Mac or the local network, also not via a redirect."""
import asyncio
import io
import socket
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0))]
TAILNET = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('100.101.102.103', 0))]
LOCAL = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 0))]


def _fetch(url):
    req = Mock()
    async def j(): return {'url': url}
    req.json = j
    return asyncio.run(app.scranton_avatar_fetch(req))


def _resolver(table):
    return lambda host, *a, **k: table[host]


class AvatarFetch(unittest.TestCase):
    def test_tailnet_address_refused(self):
        with patch('socket.getaddrinfo', _resolver({'pics.example': TAILNET})):
            r = _fetch('https://pics.example/a.png')
        self.assertEqual(r.status_code, 400)
        self.assertIn(b'local network', r.body)

    def test_redirect_to_localhost_refused(self):
        opened = []

        class FakeOpener:
            def open(self, req, timeout=None):
                opened.append(req.full_url)
                raise urllib.error.HTTPError(req.full_url, 302, 'Found', {'Location': 'http://inside.example/secret'}, io.BytesIO())

        with patch('socket.getaddrinfo', _resolver({'pics.example': PUBLIC, 'inside.example': LOCAL})), \
                patch.object(urllib.request, 'build_opener', lambda *a: FakeOpener()):
            r = _fetch('https://pics.example/a.png')
        self.assertEqual(r.status_code, 400)
        self.assertIn(b'local network', r.body)
        self.assertEqual(opened, ['https://pics.example/a.png'])   # the local address was never asked


if __name__ == '__main__':
    unittest.main()
