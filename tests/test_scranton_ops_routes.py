"""Routes declared inside install() must not mistake `request` for a query parameter (422)."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import scranton_ops


class OpsRoutesTest(unittest.TestCase):
    def test_resume_routes_accept_a_json_body(self):
        app = FastAPI()
        scranton_ops.install(app, lambda: {"agents": {}})
        c = TestClient(app)
        for path in ("/api/scranton/resume", "/api/scranton/resume/dismiss"):
            r = c.post(path, json={"names": []})
            self.assertNotEqual(r.status_code, 422, f"{path}: {r.text}")


if __name__ == "__main__":
    unittest.main()
