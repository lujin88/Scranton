"""Scranton: phones reach the app through Tailscale Serve, so the server must
accept exactly the configured extra origins and still reject every other one."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app

TOKEN = "origin-test"
TS = "https://mac-mini.tail1234.ts.net"


async def _ok():
    return JSONResponse({"ok": True})


class AllowedOriginTests(unittest.TestCase):
    def make_client(self, server_cfg):
        stack = ExitStack()
        self.addCleanup(stack.close)
        api = FastAPI()
        api.add_api_route("/api/ping", _ok, methods=["GET"])
        cfg = {"server": {"port": 8300, **server_cfg}}
        for name, value in {"app": api, "config": cfg, "registry": None,
                            "session_token": TOKEN}.items():
            stack.enter_context(patch.object(app, name, value))
        app._install_security_middleware(TOKEN, cfg)
        return stack.enter_context(TestClient(api))

    def get(self, client, origin):
        headers = {"X-Session-Token": TOKEN}
        if origin:
            headers["Origin"] = origin
        return client.get("/api/ping", headers=headers).status_code

    def test_default_only_allows_localhost(self):
        c = self.make_client({})
        self.assertEqual(self.get(c, "http://localhost:8300"), 200)
        self.assertEqual(self.get(c, TS), 403)

    def test_configured_tailscale_origin_is_allowed(self):
        c = self.make_client({"allowed_origins": [TS + "/"]})  # trailing slash tolerated
        self.assertEqual(self.get(c, TS), 200)

    def test_other_origins_still_rejected(self):
        c = self.make_client({"allowed_origins": [TS]})
        self.assertEqual(self.get(c, "https://evil.example"), 403)
        self.assertEqual(self.get(c, "https://mac-mini.tail1234.ts.net.evil.example"), 403)

    def test_token_still_required_for_allowed_origin(self):
        c = self.make_client({"allowed_origins": [TS]})
        r = c.get("/api/ping", headers={"Origin": TS})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
