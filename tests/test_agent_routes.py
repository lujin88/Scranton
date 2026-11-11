"""Every route a wrapper calls with its agent token must get through the security middleware."""
import re
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app

ROOT = Path(__file__).resolve().parent.parent


class _Reg:
    def resolve_token(self, t):
        return {"name": "pm", "base": "pm"} if t == "agent-token" else None


async def _ok():
    return JSONResponse({"ok": True})


class AgentRouteTests(unittest.TestCase):
    def test_wrapper_bearer_routes_are_allowed(self):
        src = (ROOT / "wrapper.py").read_text()
        # routes the wrapper sends with an Authorization header
        posts = set(re.findall(r'/api/scranton/[a-z-]+', src))
        for p in posts:
            if p == "/api/scranton/handover":
                continue   # GET-only exception, handled separately
            self.assertIn(p, app.AGENT_BEARER_PATHS, f"{p} is called by the wrapper with a bearer token")

    def test_limit_check_passes_middleware_with_agent_token(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        api = FastAPI()
        api.add_api_route("/api/scranton/limit-check", _ok, methods=["POST"])
        cfg = {"server": {"port": 8300}}
        reg = _Reg()
        for name, value in {"app": api, "config": cfg, "registry": reg, "session_token": "s"}.items():
            stack.enter_context(patch.object(app, name, value))
        app._install_security_middleware("s", cfg)
        c = stack.enter_context(TestClient(api, base_url="http://127.0.0.1:8300"))
        r = c.post("/api/scranton/limit-check", json={}, headers={"Authorization": "Bearer agent-token"})
        self.assertEqual(r.status_code, 200, r.text)
        r = c.post("/api/scranton/limit-check", json={}, headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status_code, 403)
