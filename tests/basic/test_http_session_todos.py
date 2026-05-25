"""HTTP API for workspace todos."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from bright_vision_core.http_api import app
from cecli.utils import GitTemporaryDirectory, make_repo
from bright_vision_core.workspace_todos import WorkspaceTodos


class TestHttpSessionTodos(unittest.TestCase):
    def test_todo_crud_and_message_active_id(self):
        with GitTemporaryDirectory() as temp_dir:
            make_repo(temp_dir)
            client = TestClient(app)
            sess = client.post(
                "/sessions",
                json={"workspace": temp_dir, "model": "gpt-4o", "auto_yes": True},
            )
            self.assertEqual(sess.status_code, 200, sess.text)
            session_id = sess.json()["session_id"]

            listed = client.get(f"/sessions/{session_id}/todos")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()["todos"], [])

            created = client.post(
                f"/sessions/{session_id}/todos",
                json={"title": "Ship it", "template": "feature"},
            )
            self.assertEqual(created.status_code, 200)
            todo_id = created.json()["id"]
            self.assertIn("## Goal", created.json()["spec"])

            active = client.put(
                f"/sessions/{session_id}/todos/active",
                json={"activeId": todo_id},
            )
            self.assertEqual(active.status_code, 200)
            self.assertEqual(active.json()["activeId"], todo_id)

            msg = client.post(
                f"/sessions/{session_id}/messages",
                json={
                    "content": "/todo list",
                    "active_todo_id": todo_id,
                    "inject_todo_spec": False,
                },
            )
            self.assertEqual(msg.status_code, 200)

            store = WorkspaceTodos(temp_dir).load()
            item = next(t for t in store.todos if t.id == todo_id)
            self.assertEqual(item.status, "in_progress")


if __name__ == "__main__":
    unittest.main()
