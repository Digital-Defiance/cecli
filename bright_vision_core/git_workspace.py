"""
Multi-repository git workspace support (superproject + submodules).

RepoSet presents a GitRepo-compatible interface while routing file operations
and commits to the correct nested repository.
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from cecli import utils
from cecli.repo import ANY_GIT_ERROR, GitRepo

from bright_vision_core.async_bridge import run
from bright_vision_core.git_undo import undo_commit_in_repo


def _ignore_file(repo: GitRepo):
    return getattr(repo, "cecli_ignore_file", None) or getattr(repo, "aider_ignore_file", None)


def _refresh_ignore(repo: GitRepo) -> None:
    if hasattr(repo, "refresh_cecli_ignore"):
        repo.refresh_cecli_ignore()
    elif hasattr(repo, "refresh_aider_ignore"):
        repo.refresh_aider_ignore()


def _repo_commit(repo: GitRepo, **kwargs):
    """Call ``GitRepo.commit`` with cecli (``coder_edits``) or legacy (``aider_edits``) kwargs."""
    if "aider_edits" in kwargs and "coder_edits" not in kwargs:
        kwargs["coder_edits"] = kwargs.pop("aider_edits")
    else:
        kwargs.pop("aider_edits", None)
    result = repo.commit(**kwargs)
    if hasattr(result, "__await__"):
        return run(result)
    return result


def _find_superproject_from_gitfile(repo_root: str) -> str | None:
    """If repo_root is a submodule checkout, return the superproject root."""
    git_path = Path(repo_root) / ".git"
    if not git_path.is_file():
        return None
    content = git_path.read_text().strip()
    if not content.startswith("gitdir:"):
        return None
    gitdir = Path(content.split(":", 1)[1].strip())
    if ".git" not in gitdir.parts:
        return None
    idx = gitdir.parts.index(".git")
    return utils.safe_abs_path(Path(*gitdir.parts[: idx + 1]).parent)


def _resolve_workspace_root(fnames, git_dname) -> str | None:
    """
    Resolve the superproject root for fnames that may span submodules.

    Returns None when paths belong to unrelated git repositories.
    """
    try:
        import git
    except ImportError:
        return None

    if git_dname:
        check_fnames = [git_dname]
    elif fnames:
        check_fnames = fnames
    else:
        check_fnames = ["."]

    repo_paths = []
    for fname in check_fnames:
        fname = Path(fname)
        fname = fname.resolve()
        if not fname.exists() and fname.parent.exists():
            fname = fname.parent
        try:
            repo_path = git.Repo(fname, search_parent_directories=True).working_dir
            repo_paths.append(utils.safe_abs_path(repo_path))
        except ANY_GIT_ERROR:
            pass

    unique = sorted(set(repo_paths), key=len)
    if not unique:
        return None
    if len(unique) == 1:
        root = unique[0]
        parent = _find_superproject_from_gitfile(root)
        return parent or root

    super_root = unique[0]
    sep = os.sep
    if all(p == super_root or p.startswith(super_root + sep) for p in unique):
        return super_root

    return None


def _parse_gitmodules_paths(gitmodules_path: Path) -> list[str]:
    if not gitmodules_path.is_file():
        return []
    paths = []
    for line in gitmodules_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("path = "):
            paths.append(line.split("=", 1)[1].strip())
    return paths


def discover_submodule_paths(super_root: str) -> list[str]:
    """
    Return submodule paths relative to the superproject root, including nested
    submodules (e.g. vendor/lib/pkg).
    """
    results: list[str] = []

    def walk(repo_root: Path, path_prefix: str) -> None:
        gitmodules = repo_root / ".gitmodules"
        if not gitmodules.is_file():
            return
        for subpath in _parse_gitmodules_paths(gitmodules):
            full_rel = f"{path_prefix}/{subpath}".strip("/") if path_prefix else subpath
            results.append(full_rel)
            sub_abs = repo_root / subpath
            if sub_abs.is_dir():
                walk(sub_abs, full_rel)

    walk(Path(super_root), "")
    return results


def _submodule_status_paths(super_root: str) -> list[str]:
    """Paths from `git submodule status --recursive` when available."""
    try:
        import git

        repo = git.Repo(super_root, odbt=git.GitDB)
        out = repo.git.submodule("status", "--recursive")
    except ANY_GIT_ERROR:
        return []
    paths = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: [+-]<sha> <path> [(describe)]
        parts = line.split()
        if len(parts) >= 2:
            paths.append(parts[1])
    return paths


def _normalize_submodule_rel_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def discover_submodule_paths_with_git(super_root: str) -> list[str]:
    """
    Submodule roots relative to the superproject, including nested (recursive) paths.

    Merges ``git submodule status --recursive`` with a ``.gitmodules`` walk so
    uninitialized or partially-checked-out nested submodules are still discovered.
    """
    root = Path(super_root)
    candidates: list[str] = []
    candidates.extend(_submodule_status_paths(super_root))
    candidates.extend(discover_submodule_paths(super_root))

    seen: set[str] = set()
    valid: list[str] = []
    for raw in candidates:
        rel = _normalize_submodule_rel_path(raw)
        if not rel or rel in seen:
            continue
        if not (root / rel).is_dir():
            continue
        seen.add(rel)
        valid.append(rel)

    # Deepest paths first (helps commit/undo ordering for nested gitlinks).
    return sorted(valid, key=lambda p: (-p.count("/"), p))


def create_git_workspace(io, fnames, git_dname, **git_repo_kwargs):
    """
    Create a GitRepo, or a RepoSet when the superproject has submodules.

    Returns GitRepo when there are no submodules (backward compatible).
    """
    workspace_root = _resolve_workspace_root(fnames, git_dname)
    if workspace_root is None:
        return GitRepo(io, fnames, git_dname, **git_repo_kwargs)

    primary = GitRepo(io, [workspace_root], git_dname, **git_repo_kwargs)
    sub_paths = discover_submodule_paths_with_git(primary.root)
    if not sub_paths:
        return primary
    return RepoSet(io, primary, sub_paths, **git_repo_kwargs)


def primary_head_from_snapshot(snapshot, primary_root: str):
    """Extract superproject HEAD sha from a commit snapshot."""
    if isinstance(snapshot, dict):
        return snapshot.get(primary_root)
    return snapshot


class RepoSet:
    """
    GitRepo-compatible facade over a superproject and its submodules.

    Commits run innermost repositories first, then update parent gitlinks.
    """

    def __init__(self, io, primary: GitRepo, submodule_paths: list[str], **git_repo_kwargs):
        self.io = io
        self.primary = primary
        self.root = primary.root
        self.repo = primary.repo
        self.aider_ignore_file = _ignore_file(primary)
        self.cecli_ignore_file = self.aider_ignore_file
        self.subtree_only = primary.subtree_only

        self.repos: list[GitRepo] = [primary]
        seen_roots = {primary.root}

        # submodule_paths are deepest-first; init every nested checkout we can open.
        for rel_path in submodule_paths:
            abs_path = Path(primary.root) / rel_path
            if not abs_path.is_dir():
                continue
            try:
                sub = GitRepo(io, [str(abs_path)], None, **git_repo_kwargs)
            except FileNotFoundError:
                continue
            if sub.root in seen_roots:
                continue
            seen_roots.add(sub.root)
            self.repos.append(sub)

        self.repos.sort(key=lambda r: len(Path(r.root).parts), reverse=True)
        self.last_commit_batch: list[dict] = []
        self.submodule_rel_paths = frozenset(
            _normalize_submodule_rel_path(p) for p in submodule_paths
        )

    def repo_by_root(self, root: str) -> GitRepo | None:
        for repo in self.repos:
            if repo.root == root:
                return repo
        return None

    @property
    def git_repo_error(self):
        return self.primary.git_repo_error

    @git_repo_error.setter
    def git_repo_error(self, value):
        self.primary.git_repo_error = value

    def _abs_path(self, path: str) -> Path:
        path = str(path)
        p = Path(path)
        if p.is_absolute():
            return Path(utils.safe_abs_path(p))
        return Path(utils.safe_abs_path(Path(self.root) / path))

    def repo_for_abs_path(self, path: str) -> GitRepo:
        abs_path = self._abs_path(path)
        best = self.primary
        best_len = -1
        for repo in self.repos:
            root = Path(repo.root)
            try:
                abs_path.relative_to(root)
            except ValueError:
                continue
            root_len = len(str(root))
            if root_len > best_len:
                best = repo
                best_len = root_len
        return best

    def repo_for_rel_path(self, path: str) -> GitRepo:
        return self.repo_for_abs_path(path)

    def path_relative_to_repo(self, path: str, repo: GitRepo | None = None) -> str:
        repo = repo or self.repo_for_rel_path(path)
        abs_path = self._abs_path(path)
        rel = abs_path.relative_to(Path(repo.root))
        return rel.as_posix()

    def path_in_workspace(self, path: str) -> str:
        """Path relative to the superproject (workspace) root."""
        abs_path = self._abs_path(path)
        return abs_path.relative_to(Path(self.root)).as_posix()

    def normalize_path(self, path):
        return self.primary.normalize_path(self.path_in_workspace(path))

    def path_in_repo(self, path):
        repo = self.repo_for_rel_path(path)
        rel = self.path_relative_to_repo(path, repo)
        return repo.path_in_repo(rel)

    def get_tracked_files(self):
        files: set[str] = set()
        primary_root = Path(self.primary.root)
        for repo in self.repos:
            prefix = Path(os.path.relpath(repo.root, primary_root))
            if str(prefix) == ".":
                prefix = Path("")
            for fname in repo.get_tracked_files():
                posix_fname = fname.replace("\\", "/")
                if not prefix:
                    workspace_rel = posix_fname
                    if workspace_rel in self.submodule_rel_paths:
                        continue
                    if self.primary.is_submodule_gitlink(posix_fname):
                        continue
                elif prefix:
                    workspace_rel = f"{prefix.as_posix()}/{posix_fname}"
                    if workspace_rel in self.submodule_rel_paths:
                        continue
                if prefix:
                    files.add((prefix / fname).as_posix())
                else:
                    files.add(fname)
        for sub_path in self.submodule_rel_paths:
            files.discard(sub_path)
        return sorted(files)

    def abs_root_path(self, path):
        return str(self._abs_path(path))

    def ignored_file(self, fname):
        return self.primary.ignored_file(self.path_in_workspace(str(fname)))

    def git_ignored_file(self, path):
        repo = self.repo_for_rel_path(str(path))
        rel = self.path_relative_to_repo(str(path), repo)
        return repo.git_ignored_file(rel)

    def is_dirty(self, path=None):
        if path is not None:
            repo = self.repo_for_rel_path(str(path))
            rel = self.path_relative_to_repo(str(path), repo)
            return repo.is_dirty(rel)
        return any(r.repo.is_dirty() for r in self.repos)

    def get_dirty_files(self):
        dirty: set[str] = set()
        primary_root = Path(self.primary.root)
        for repo in self.repos:
            prefix = Path(os.path.relpath(repo.root, primary_root))
            if str(prefix) == ".":
                prefix = Path("")
            for fname in repo.get_dirty_files():
                if prefix:
                    dirty.add((prefix / fname).as_posix())
                else:
                    dirty.add(fname)
        return list(dirty)

    def commit(self, fnames=None, context=None, message=None, aider_edits=False, coder=None):
        if fnames:
            return self._commit_files(
                list(fnames),
                context=context,
                message=message,
                aider_edits=aider_edits,
                coder=coder,
            )

        if not self.is_dirty():
            return None

        dirty_by_repo: dict[GitRepo, list[str]] = defaultdict(list)
        for repo in self.repos:
            for fname in repo.get_dirty_files():
                dirty_by_repo[repo].append(fname)

        return self._commit_by_repo_map(
            dirty_by_repo,
            context=context,
            message=message,
            aider_edits=aider_edits,
            coder=coder,
        )

    def _commit_files(self, fnames, context=None, message=None, aider_edits=False, coder=None):
        by_repo: dict[GitRepo, list[str]] = defaultdict(list)
        for fname in fnames:
            repo = self.repo_for_rel_path(fname)
            by_repo[repo].append(self.path_relative_to_repo(fname, repo))
        return self._commit_by_repo_map(
            by_repo,
            context=context,
            message=message,
            aider_edits=aider_edits,
            coder=coder,
        )

    def _commit_by_repo_map(
        self, by_repo, context=None, message=None, aider_edits=False, coder=None
    ):
        self.last_commit_batch = []
        last_result = None
        committed_repos: list[GitRepo] = []

        for repo in self.repos:
            repo_fnames = by_repo.get(repo)
            if not repo_fnames:
                continue
            res = _repo_commit(
                repo,
                fnames=repo_fnames,
                context=context,
                message=message,
                aider_edits=aider_edits,
                coder=coder,
            )
            if res:
                last_result = res
                committed_repos.append(repo)
                self._record_commit(repo, res)

        if not committed_repos:
            return last_result

        self._commit_submodule_pointer_updates(
            committed_repos, context, message, aider_edits, coder
        )
        return last_result

    def _record_commit(self, repo: GitRepo, res: tuple) -> None:
        commit_hash, commit_message = res
        self.last_commit_batch.append(
            {
                "root": repo.root,
                "hash": commit_hash,
                "message": commit_message,
            }
        )

    def _commit_submodule_pointer_updates(
        self, committed_repos, context=None, message=None, aider_edits=False, coder=None
    ):
        primary_root = Path(self.primary.root)
        for repo in committed_repos:
            if repo is self.primary:
                continue
            try:
                rel_sub = Path(repo.root).relative_to(primary_root).as_posix()
            except ValueError:
                continue
            if not self.primary.repo.is_dirty(path=rel_sub):
                continue
            res = _repo_commit(
                self.primary,
                fnames=[rel_sub],
                context=context,
                message=message,
                aider_edits=aider_edits,
                coder=coder,
            )
            if res:
                self._record_commit(self.primary, res)

    def undo_last_aider_commit(self, coder, io):
        """
        Undo the most recent batch of aider commits (superproject + submodules).
        """
        from cecli import prompts

        if coder.aider_commit_stack:
            batch = coder.aider_commit_stack[-1]
            for entry in reversed(batch):
                commit_hash = entry["hash"]
                if commit_hash not in coder.aider_commit_hashes:
                    io.tool_error("The last commit was not made by aider in this chat session.")
                    return
                git_repo = self.repo_by_root(entry["root"])
                if not git_repo:
                    io.tool_error(f"Unknown repository root: {entry['root']}")
                    return
                if not undo_commit_in_repo(git_repo, io, expected_hash=commit_hash):
                    return
                coder.aider_commit_hashes.discard(commit_hash)

            coder.aider_commit_stack.pop()
            if coder.aider_commit_stack:
                last = coder.aider_commit_stack[-1][-1]
                coder.last_aider_commit_hash = last["hash"]
                coder.last_aider_commit_message = last["message"]
            else:
                coder.last_aider_commit_hash = None
                coder.last_aider_commit_message = None

            if coder.main_model.send_undo_reply:
                return prompts.undo_command_reply
            return

        git_repo = self.primary
        last_commit_hash = git_repo.get_head_commit_sha(short=True)
        if last_commit_hash not in coder.aider_commit_hashes:
            io.tool_error("The last commit was not made by aider in this chat session.")
            io.tool_output(
                "You could try `/git reset --hard HEAD^` but be aware that this is a destructive"
                " command!"
            )
            return

        if undo_commit_in_repo(git_repo, io, expected_hash=last_commit_hash):
            coder.aider_commit_hashes.discard(last_commit_hash)
            coder.last_aider_commit_hash = None
            coder.last_aider_commit_message = None
            if coder.main_model.send_undo_reply:
                return prompts.undo_command_reply

    def get_diffs(self, fnames=None):
        return self.primary.get_diffs(fnames)

    def diff_commits(self, pretty, from_commit, to_commit):
        return self.primary.diff_commits(pretty, from_commit, to_commit)

    def get_rel_repo_dir(self):
        return self.primary.get_rel_repo_dir()

    def get_head_commit(self):
        return self.primary.get_head_commit()

    def get_head_commit_sha(self, short=False):
        return self.primary.get_head_commit_sha(short=short)

    def get_head_commit_message(self, default=None):
        return self.primary.get_head_commit_message(default=default)

    def get_commit_snapshot(self):
        """Head SHAs for superproject and every nested repo (for undo/diff)."""
        return {repo.root: repo.get_head_commit_sha() for repo in self.repos}

    def refresh_aider_ignore(self):
        _refresh_ignore(self.primary)

    def refresh_cecli_ignore(self):
        _refresh_ignore(self.primary)

    def get_commit_message(self, diffs, context, user_language=None):
        return self.primary.get_commit_message(diffs, context, user_language)
