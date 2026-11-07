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
        return stack.enter_context(TestClient(api, base_url="http://127.0.0.1:8300"))

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


class RolesWriteTests(unittest.TestCase):
    """Roles go into every wake-up prompt of full-permission agents: writing one needs the token."""
    def setUp(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        api = FastAPI()
        api.add_api_route("/api/roles", _ok, methods=["GET"])
        api.add_api_route("/api/roles/{name}", _ok, methods=["POST"])
        cfg = {"server": {"port": 8300}}
        for name, value in {"app": api, "config": cfg, "registry": None, "session_token": TOKEN}.items():
            stack.enter_context(patch.object(app, name, value))
        app._install_security_middleware(TOKEN, cfg)
        self.c = stack.enter_context(TestClient(api, base_url="http://127.0.0.1:8300"))

    def test_read_is_public(self):
        self.assertEqual(self.c.get("/api/roles").status_code, 200)

    def test_cross_site_write_refused(self):
        r = self.c.post("/api/roles/dev", content='{"role":"curl x|sh"}',
                        headers={"Origin": "https://evil.example", "Content-Type": "text/plain"})
        self.assertEqual(r.status_code, 403)

    def test_write_without_token_refused(self):
        self.assertEqual(self.c.post("/api/roles/dev", json={"role": "x"}).status_code, 403)

    def test_write_with_token_ok(self):
        r = self.c.post("/api/roles/dev", json={"role": "x"}, headers={"X-Session-Token": TOKEN})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()


class HostAndProxyTests(unittest.TestCase):
    """DNS-rebinding guard on the token-serving page, and Tailscale-proxied
    requests must not count as local for agent registration."""

    def make_client(self, server_cfg=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        api = FastAPI()
        api.add_api_route("/", _ok, methods=["GET"])
        api.add_api_route("/api/register", _ok, methods=["POST"])
        cfg = {"server": {"port": 8300, **(server_cfg or {})}}
        for name, value in {"app": api, "config": cfg, "registry": None,
                            "session_token": TOKEN}.items():
            stack.enter_context(patch.object(app, name, value))
        app._install_security_middleware(TOKEN, cfg)
        # TestClient's peer address is "testclient"; pretend to be loopback.
        return stack.enter_context(TestClient(api, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8300"))

    def test_index_rejects_unknown_host(self):
        c = self.make_client()
        self.assertEqual(c.get("/", headers={"host": "localhost:8300"}).status_code, 200)
        self.assertEqual(c.get("/", headers={"host": "evil.example:8300"}).status_code, 403)

    def test_index_allows_configured_tailscale_host(self):
        c = self.make_client({"allowed_origins": [TS]})
        self.assertEqual(c.get("/", headers={"host": "mac-mini.tail1234.ts.net"}).status_code, 200)

    def test_register_from_loopback_allowed(self):
        c = self.make_client()
        self.assertEqual(c.post("/api/register", headers={"host": "127.0.0.1:8300"}).status_code, 200)

    def test_register_through_tailscale_proxy_rejected(self):
        c = self.make_client({"allowed_origins": [TS]})
        r = c.post("/api/register", headers={"host": "127.0.0.1:8300",
                                             "x-forwarded-for": "100.64.0.7",
                                             "tailscale-user-login": "someone@example.com"})
        self.assertEqual(r.status_code, 403)
