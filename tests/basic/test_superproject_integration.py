"""
Integration checks for BrightVision superproject + bright-vision-core submodule.

Skipped unless the parent repo layout exists (dev checkout).
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[2]
SUPERPROJECT = Path(os.environ.get("BRIGHT_VISION_SUPERPROJECT", CORE_ROOT.parent))
ENGINE_DIR = "bright-vision-core"
PKG_REL = f"{ENGINE_DIR}/bright_vision_core/session.py"


def _have_superproject_layout() -> bool:
    return (SUPERPROJECT / ENGINE_DIR).is_dir() and (SUPERPROJECT / ".git").exists()


@unittest.skipUnless(_have_superproject_layout(), "requires bright-vision superproject checkout")
class TestBrightVisionSubmoduleLayout(unittest.TestCase):
    def test_repo_set_and_submodule_paths(self):
        from bright_vision_core.event_io import EventIO
        from bright_vision_core.git_workspace import RepoSet, create_git_workspace, discover_submodule_paths

        io = EventIO(yes=True, echo_to_console=False)
        paths = discover_submodule_paths(str(SUPERPROJECT))
        self.assertIn(ENGINE_DIR, paths)

        ws = create_git_workspace(io, [], str(SUPERPROJECT))
        self.assertIsInstance(ws, RepoSet)

        self.assertTrue(ws.path_in_repo(PKG_REL))
        sub = ws.repo_for_rel_path(PKG_REL)
        self.assertTrue(str(sub.root).endswith(ENGINE_DIR))

    def test_session_create_adds_submodule_file(self):
        from bright_vision_core.session import Session

        session = Session.create(
            str(SUPERPROJECT),
            files=[str(SUPERPROJECT / PKG_REL)],
            yes=True,
            dry_run=True,
        )
        self.assertEqual(Path(session.coder.root).resolve(), SUPERPROJECT.resolve())
        inchat = session.coder.get_inchat_relative_files()
        self.assertIn(PKG_REL.replace("\\", "/"), [p.replace("\\", "/") for p in inchat])


if __name__ == "__main__":
    unittest.main()
