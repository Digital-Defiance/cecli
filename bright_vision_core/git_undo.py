"""
Undo a single aider-style commit in one git repository.
"""

from __future__ import annotations

from cecli import prompts
from cecli.repo import ANY_GIT_ERROR, GitRepo


def _hash_matches(expected: str | None, short_hash: str | None, full_hex: str | None) -> bool:
    if not expected:
        return True
    if short_hash and (expected == short_hash or full_hex.startswith(expected)):
        return True
    if full_hex and expected == full_hex:
        return True
    return False


def undo_commit_in_repo(git_repo: GitRepo, io, expected_hash: str | None = None) -> bool:
    last_commit = git_repo.get_head_commit()
    if not last_commit or not last_commit.parents:
        io.tool_error("This is the first commit in the repository. Cannot undo.")
        return False

    last_commit_hash = git_repo.get_head_commit_sha(short=True)
    full_hex = last_commit.hexsha
    if expected_hash and not _hash_matches(expected_hash, last_commit_hash, full_hex):
        io.tool_error(
            f"HEAD ({last_commit_hash}) is not the expected commit ({expected_hash}). Cannot undo."
        )
        return False

    last_commit_message = git_repo.get_head_commit_message("(unknown)").strip()
    last_commit_message = (last_commit_message.splitlines() or [""])[0]

    if len(last_commit.parents) > 1:
        io.tool_error(f"The last commit {full_hex} has more than 1 parent, can't undo.")
        return False

    prev_commit = last_commit.parents[0]
    changed_files_last_commit = [item.a_path for item in last_commit.diff(prev_commit)]

    for fname in changed_files_last_commit:
        if git_repo.repo.is_dirty(path=fname):
            io.tool_error(
                f"The file {fname} has uncommitted changes. Please stash them before undoing."
            )
            return False
        try:
            prev_commit.tree[fname]
        except KeyError:
            io.tool_error(
                f"The file {fname} was not in the repository in the previous commit. Cannot"
                " undo safely."
            )
            return False

    local_head = git_repo.repo.git.rev_parse("HEAD")
    try:
        current_branch = git_repo.repo.active_branch.name
        remote_head = git_repo.repo.git.rev_parse(f"origin/{current_branch}")
        has_origin = True
    except ANY_GIT_ERROR:
        has_origin = False

    if has_origin and local_head == remote_head:
        io.tool_error(
            "The last commit has already been pushed to the origin. Undoing is not possible."
        )
        return False

    restored = set()
    unrestored = set()
    for file_path in changed_files_last_commit:
        try:
            git_repo.repo.git.checkout("HEAD~1", file_path)
            restored.add(file_path)
        except ANY_GIT_ERROR:
            unrestored.add(file_path)

    if unrestored:
        io.tool_error("Error restoring files, aborting undo.")
        io.tool_output("Restored files:")
        for file in restored:
            io.tool_output(f"  {file}")
        io.tool_output("Unable to restore files:")
        for file in unrestored:
            io.tool_output(f"  {file}")
        return False

    git_repo.repo.git.reset("--soft", "HEAD~1")
    io.tool_output(f"Removed: {last_commit_hash} {last_commit_message}")

    current_head_hash = git_repo.get_head_commit_sha(short=True)
    current_head_message = git_repo.get_head_commit_message("(unknown)").strip()
    current_head_message = (current_head_message.splitlines() or [""])[0]
    io.tool_output(f"Now at:  {current_head_hash} {current_head_message}")
    return True


def undo_last_aider_commit_for_coder(coder, io):
    """Undo the last agent commit batch for any repository layout."""
    repo = coder.repo
    if not repo:
        io.tool_error("No git repository found.")
        return

    if hasattr(repo, "undo_last_aider_commit"):
        return repo.undo_last_aider_commit(coder, io)

    commit_stack = getattr(coder, "aider_commit_stack", None) or []
    commit_hashes = getattr(coder, "aider_commit_hashes", None) or set()

    if commit_stack:
        batch = commit_stack[-1]
        for entry in reversed(batch):
            if entry["hash"] not in commit_hashes:
                io.tool_error("The last commit was not made by aider in this chat session.")
                return
            if entry["root"] != repo.root:
                io.tool_error("Repository layout changed since commit. Cannot undo safely.")
                return
            if not undo_commit_in_repo(repo, io, expected_hash=entry["hash"]):
                return
            commit_hashes.discard(entry["hash"])
        commit_stack.pop()
        _refresh_last_aider_commit_fields(coder)
        if coder.main_model.send_undo_reply:
            return prompts.undo_command_reply
        return

    last_commit_hash = repo.get_head_commit_sha(short=True)
    if last_commit_hash not in commit_hashes:
        io.tool_error("The last commit was not made by aider in this chat session.")
        io.tool_output(
            "You could try `/git reset --hard HEAD^` but be aware that this is a destructive"
            " command!"
        )
        return

    if undo_commit_in_repo(repo, io, expected_hash=last_commit_hash):
        commit_hashes.discard(last_commit_hash)
        coder.last_aider_commit_hash = None
        coder.last_aider_commit_message = None
        if coder.main_model.send_undo_reply:
            return prompts.undo_command_reply


def _refresh_last_aider_commit_fields(coder) -> None:
    stack = getattr(coder, "aider_commit_stack", None) or []
    if stack:
        last = stack[-1][-1]
        coder.last_aider_commit_hash = last["hash"]
        coder.last_aider_commit_message = last["message"]
    else:
        coder.last_aider_commit_hash = None
        coder.last_aider_commit_message = None
