import subprocess
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from bright_vision_core.git_workspace import (
    RepoSet,
    _submodule_status_paths,
    create_git_workspace,
    discover_submodule_paths,
)
from bright_vision_core.git_undo import undo_last_aider_commit_for_coder
from cecli.io import InputOutput
from cecli.repo import GitRepo
from cecli.utils import GitTemporaryDirectory, make_repo


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_submodule(super_root: Path, name: str, sub_files: dict[str, str] | None = None):
    """Add a submodule at `name` with optional {relative_path: content} files."""
    sub_files = sub_files or {"hello.txt": "hello\n"}
    sub_path = super_root / name
    sub_path.mkdir(parents=True, exist_ok=True)
    for rel, content in sub_files.items():
        f = sub_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)

    _git("init", cwd=sub_path)
    _git("config", "user.email", "sub@test.com", cwd=sub_path)
    _git("config", "user.name", "Sub User", cwd=sub_path)
    for rel in sub_files:
        _git("add", rel, cwd=sub_path)
    _git("commit", "-m", "init submodule repo", cwd=sub_path)

    _git("submodule", "add", str(sub_path), name, cwd=super_root)
    _git("commit", "-m", f"add submodule {name}", cwd=super_root)


class TestGitWorkspace(unittest.TestCase):
    def test_discover_submodule_paths(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib")
            paths = discover_submodule_paths(str(root))
            self.assertIn("vendor/lib", paths)

    def test_create_git_workspace_no_submodules(self):
        with GitTemporaryDirectory():
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(io, None, None)
            self.assertIsInstance(ws, GitRepo)

    def test_create_git_workspace_with_submodule(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(io, [str(root)], None)
            self.assertIsInstance(ws, RepoSet)
            self.assertEqual(len(ws.repos), 2)

    def test_path_in_repo_submodule_file(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(io, [str(root)], None)
            self.assertTrue(ws.path_in_repo("vendor/lib/pkg.py"))

    def test_get_tracked_files_includes_submodule(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(io, [str(root)], None)
            tracked = ws.get_tracked_files()
            self.assertIn("vendor/lib/pkg.py", tracked)

    def test_get_tracked_files_excludes_submodule_gitlink(self):
        """Superproject gitlink paths are directories, not repo-map files."""
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(io, [str(root)], None)
            tracked = ws.get_tracked_files()
            self.assertNotIn("vendor/lib", tracked)
            self.assertIn("vendor/lib/pkg.py", tracked)

    def test_submodule_status_path_not_describe_tag(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            paths = _submodule_status_paths(str(root))
            self.assertIn("vendor/lib", paths)
            self.assertTrue(all(not p.startswith("(") for p in paths))

    def test_submodule_status_parses_nested_paths(self):
        lines = (
            " abc1234 vendor/lib (v1.0.0)\n"
            " def5678 vendor/lib/pkg (heads/main)\n"
        )
        with patch("git.Repo") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.git.submodule.return_value = lines
            paths = _submodule_status_paths("/tmp/ws")
        self.assertEqual(paths, ["vendor/lib", "vendor/lib/pkg"])

    def test_commit_inside_submodule_updates_pointer(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(io, [str(root)], None)

            sub_file = root / "vendor/lib/pkg.py"
            sub_file.write_text("x = 2\n")

            res = ws.commit(fnames=["vendor/lib/pkg.py"], message="update pkg", aider_edits=True)
            self.assertIsNotNone(res)

            sub_repo = ws.repo_for_rel_path("vendor/lib/pkg.py")
            self.assertFalse(sub_repo.is_dirty("pkg.py"))

            self.assertFalse(ws.primary.repo.is_dirty(path="vendor/lib"))

    def test_resolve_workspace_root_mixed_paths(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            (root / "README.md").write_text("# root\n")
            _git("add", "README.md", cwd=root)
            _git("commit", "-m", "readme", cwd=root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(
                io,
                [str(root / "vendor/lib/pkg.py"), str(root / "README.md")],
                None,
            )
            self.assertIsInstance(ws, RepoSet)

    def test_fnames_only_in_submodule(self):
        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            # Match Session.create: superproject git_dname + file inside submodule
            ws = create_git_workspace(
                io, [str(root / "vendor/lib/pkg.py")], str(root)
            )
            self.assertIsInstance(ws, RepoSet)
            self.assertEqual(ws.root, str(root.resolve()))

    @patch("cecli.models.Model.simple_send_with_retries")
    def test_undo_submodule_commit_batch(self, mock_send):
        mock_send.return_value = '"update pkg"'

        with GitTemporaryDirectory() as root:
            root = Path(root)
            _init_submodule(root, "vendor/lib", {"pkg.py": "x = 1\n"})
            io = InputOutput(pretty=False, yes=True)
            ws = create_git_workspace(
                io,
                [str(root)],
                str(root),
                models=[],
            )
            self.assertIsInstance(ws, RepoSet)

            sub_file = root / "vendor/lib/pkg.py"
            sub_file.write_text("x = 99\n")

            res = ws.commit(
                fnames=["vendor/lib/pkg.py"],
                aider_edits=True,
                message="update pkg",
            )
            self.assertIsNotNone(res)
            self.assertGreaterEqual(len(ws.last_commit_batch), 1)

            coder = types.SimpleNamespace(
                repo=ws,
                aider_commit_hashes={e["hash"] for e in ws.last_commit_batch},
                aider_commit_stack=[list(ws.last_commit_batch)],
                last_aider_commit_hash=ws.last_commit_batch[-1]["hash"],
                last_aider_commit_message=ws.last_commit_batch[-1]["message"],
                main_model=types.SimpleNamespace(send_undo_reply=False),
            )

            undo_last_aider_commit_for_coder(coder, io)
            self.assertEqual(coder.aider_commit_stack, [])
            self.assertEqual(sub_file.read_text(), "x = 1\n")


if __name__ == "__main__":
    unittest.main()
