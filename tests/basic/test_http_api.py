import os
import unittest

try:
    from fastapi.testclient import TestClient

    from bright_vision_core.http_api import app, _sessions
    from bright_vision_core.http_auth import configure_auth, reset_auth_for_tests
except ImportError:
    TestClient = None
    app = None
    configure_auth = None
    reset_auth_for_tests = None

from cecli.utils import GitTemporaryDirectory


@unittest.skipIf(TestClient is None, "fastapi not installed")
class TestHttpApi(unittest.TestCase):
    def setUp(self):
        _sessions.clear()
        reset_auth_for_tests()
        configure_auth("127.0.0.1")

    def tearDown(self):
        reset_auth_for_tests()
        os.environ.pop("AIDER_VISION_TOKEN", None)

    def test_health(self):
        client = TestClient(app)
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_create_session_missing_workspace(self):
        client = TestClient(app)
        res = client.post("/sessions", json={"workspace": "/nonexistent/path/xyz"})
        self.assertEqual(res.status_code, 404)

    def test_auth_required_when_token_set(self):
        os.environ["AIDER_VISION_TOKEN"] = "test-secret-token"
        configure_auth("127.0.0.1")
        client = TestClient(app)
        res = client.post("/sessions", json={"workspace": "/tmp"})
        self.assertEqual(res.status_code, 401)
        res = client.post(
            "/sessions",
            json={"workspace": "/tmp"},
            headers={"Authorization": "Bearer test-secret-token"},
        )
        self.assertIn(res.status_code, (200, 400, 404))

    def test_create_and_delete_session(self):
        with GitTemporaryDirectory() as root:
            client = TestClient(app)
            res = client.post("/sessions", json={"workspace": root, "model": "gpt-4o"})
            if res.status_code == 400:
                self.skipTest(f"Could not create session (model/env): {res.text}")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            session_id = data["session_id"]
            self.assertTrue(session_id)

            res = client.get(f"/sessions/{session_id}")
            self.assertEqual(res.status_code, 200)

            res = client.delete(f"/sessions/{session_id}")
            self.assertEqual(res.status_code, 200)

            res = client.get(f"/sessions/{session_id}")
            self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
