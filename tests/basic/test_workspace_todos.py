import unittest
from pathlib import Path

from cecli.utils import GitTemporaryDirectory, make_repo
from bright_vision_core.workspace_todos import WorkspaceTodos


class TestWorkspaceTodos(unittest.TestCase):
    def test_roundtrip(self):
        with GitTemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_repo(root)
            api = WorkspaceTodos(root)
            item = api.add("Ship feature", template="feature")
            self.assertIn("## Goal", item.spec)
            self.assertTrue(api.path.is_file())
            store = api.load()
            self.assertEqual(len(store.todos), 1)
            self.assertEqual(store.todos[0].title, "Ship feature")
            api.set_active(item.id)
            store = api.load()
            self.assertEqual(store.active_id, item.id)
            api.append_links(["src/foo.ts", "commit:abc123"])
            store = api.load()
            self.assertIn("src/foo.ts", store.todos[0].links)
            api.mark_done(item.id)
            store = api.load()
            self.assertEqual(store.todos[0].status, "done")
            self.assertIsNone(store.active_id)

    def test_move_reorders(self):
        with GitTemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_repo(root)
            api = WorkspaceTodos(root)
            a = api.add("First")
            b = api.add("Second")
            store = api.load()
            self.assertEqual(store.todos[0].id, b.id)
            api.move(b.id, "down")
            store = api.load()
            self.assertEqual(store.todos[0].id, a.id)
            self.assertEqual(store.todos[1].id, b.id)

    def test_import_spec_files(self):
        with GitTemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            make_repo(root)
            api = WorkspaceTodos(root)
            item = api.add("Spec task", template="spec-driven")
            api.sync_spec_files(item)
            spec_dir = root / ".aider-vision" / "specs" / item.id
            (spec_dir / "requirements.md").write_text("### REQ-1\nUpdated", encoding="utf-8")
            loaded = api.import_spec_files(item.id)
            self.assertIn("Updated", loaded.requirements)


if __name__ == "__main__":
    unittest.main()
