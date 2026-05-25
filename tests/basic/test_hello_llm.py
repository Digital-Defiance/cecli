"""Real Ollama turn — opt-in with E2E_LLM=1 (same stack as e2e/hello-llm.spec.ts)."""

from __future__ import annotations

import json
import os
import unittest
from urllib.error import URLError
from urllib.request import urlopen

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


def _ollama_host() -> str:
    return (
        os.environ.get("E2E_OLLAMA_HOST")
        or os.environ.get("OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def _first_pulled_tag() -> str | None:
    try:
        with urlopen(f"{_ollama_host()}/api/tags", timeout=10) as res:
            body = json.loads(res.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    models = body.get("models") or []
    if not models:
        return None
    entry = models[0]
    return entry.get("name") or entry.get("model")


def _ollama_tag() -> str:
    explicit = (os.environ.get("E2E_OLLAMA_MODEL") or "").strip()
    if explicit.startswith("ollama_chat/"):
        return explicit[len("ollama_chat/") :]
    if explicit.startswith("ollama/"):
        return explicit[len("ollama/") :]
    if explicit:
        return explicit
    data = (os.environ.get("DATA_MODEL") or "").strip()
    if data:
        if data.startswith("ollama_chat/"):
            return data[len("ollama_chat/") :]
        if data.startswith("ollama/"):
            return data[len("ollama/") :]
        return data
    fallback = _first_pulled_tag()
    if fallback:
        return fallback
    return "llama3.2:3b"


def _vision_model() -> str:
    tag = _ollama_tag()
    if tag.startswith("ollama_chat/"):
        return tag
    return f"ollama_chat/{tag}"


def _ollama_reachable() -> bool:
    host = (os.environ.get("E2E_OLLAMA_HOST") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip(
        "/"
    )
    try:
        with urlopen(f"{host}/api/tags", timeout=10) as res:
            return res.status == 200
    except (URLError, TimeoutError, OSError):
        return False


def _parse_sse_payload(raw: str) -> list[dict]:
    events: list[dict] = []
    for part in raw.split("\n\n"):
        for line in part.split("\n"):
            if not line.startswith("data: "):
                continue
            events.append(json.loads(line[6:]))
    return events


@unittest.skipIf(TestClient is None, "fastapi not installed")
@unittest.skipIf(os.environ.get("E2E_LLM") != "1", "set E2E_LLM=1 to run real LLM tests")
@unittest.skipIf(not _ollama_reachable(), "Ollama not reachable")
class TestHelloLlm(unittest.TestCase):
    def setUp(self):
        _sessions.clear()
        reset_auth_for_tests()
        configure_auth("127.0.0.1")

    def tearDown(self):
        reset_auth_for_tests()

    def test_hello_message_streams_tokens_and_done(self):
        model = _vision_model()
        with GitTemporaryDirectory() as root:
            client = TestClient(app)
            res = client.post("/sessions", json={"workspace": root, "model": model})
            if res.status_code == 400:
                self.skipTest(f"Could not create session: {res.text}")
            self.assertEqual(res.status_code, 200, res.text)
            session_id = res.json()["session_id"]

            with client.stream(
                "POST",
                f"/sessions/{session_id}/messages",
                json={"content": "Reply with exactly: hello from pytest", "preproc": True},
            ) as stream:
                self.assertEqual(stream.status_code, 200)
                body = stream.read().decode("utf-8")

            events = _parse_sse_payload(body)
            types = [e.get("type") for e in events]
            errors = [e for e in events if e.get("type") == "error"]
            self.assertFalse(errors, errors)
            self.assertIn("user_message", types)
            self.assertIn("done", types, f"events: {types}")
            tokens = [e.get("text", "") for e in events if e.get("type") == "token"]
            assistant = "".join(tokens)
            done = next(e for e in events if e.get("type") == "done")
            if not assistant:
                assistant = done.get("assistant_text") or ""
            self.assertTrue(
                len(assistant.strip()) > 3,
                f"expected non-empty assistant text, got {assistant!r}",
            )
            self.assertFalse(done.get("error"), done)


if __name__ == "__main__":
    unittest.main()
