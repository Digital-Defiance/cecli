"""
Headless cecli sessions for API / web frontends.
"""

from __future__ import annotations

import base64
import os
import shlex
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterator, TypeVar

_T = TypeVar("_T")

from cecli import models
from cecli.coders import Coder
from cecli.commands import Commands

from bright_vision_core.async_bridge import (
    HEARTBEAT_PULSE,
    iterate_async_with_heartbeats,
    rebind_coder_loop_primitives,
    run,
)
from bright_vision_core.gui_progress import emit_progress
from bright_vision_core.event_io import EventIO
from bright_vision_core.git_undo import undo_last_aider_commit_for_coder
from bright_vision_core.git_workspace import create_git_workspace
from bright_vision_core.headless_args import default_headless_args
from bright_vision_core.todo_spec_generate import build_generate_message, parse_generated_layers
from bright_vision_core.slash_helpers import is_switch_coder_signal, run_slash_command_sync
from bright_vision_core.workspace_todos import WorkspaceTodos, format_todo_context


def _edited_files(coder) -> list[str]:
    raw = (
        getattr(coder, "aider_edited_files", None)
        or getattr(coder, "files_edited_by_tools", None)
        or getattr(coder, "coder_edited_files", None)
        or set()
    )
    return sorted(raw) if raw else []


def _done_commit_fields(coder) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    last_hash = getattr(coder, "last_aider_commit_hash", None)
    last_msg = getattr(coder, "last_aider_commit_message", None)
    if last_hash:
        payload["commit_hash"] = last_hash
        payload["commit_message"] = last_msg
    stack = getattr(coder, "aider_commit_stack", None)
    if stack:
        payload["commits"] = stack[-1]
    return payload


def _drain_io_events(io: EventIO) -> Iterator[dict[str, Any]]:
    for event in io.drain_events():
        yield event


def _run_blocking_with_sse_pulses(
    io: EventIO,
    fn: Callable[[], _T],
    *,
    label: str = "Vision",
    message: str = "Working…",
    interval_s: float = 8.0,
) -> Iterator[dict[str, Any] | _T]:
    """Run blocking work in a thread; emit progress and yield so SSE stays alive."""
    wait_s = max(2.0, interval_s)
    done = threading.Event()
    result: list[_T] = []
    error: list[BaseException] = []

    def worker() -> None:
        try:
            result.append(fn())
        except BaseException as err:
            error.append(err)
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()
    pulse = 0
    while not done.wait(timeout=wait_s):
        pulse += 1
        emit_progress(io, label=label, message=f"{message} ({int(pulse * wait_s)}s)")
        yield from _drain_io_events(io)
    if error:
        raise error[0]
    yield from _drain_io_events(io)
    yield result[0]


class Session:
    """A headless coder session with event-streaming support."""

    def __init__(self, coder: Coder, io: EventIO):
        self.coder = coder
        self.io = io
        self.coder.yield_stream = True
        self.coder.stream = bool(coder.stream)
        self.coder.pretty = False
        self.coder.commands.io = io
        self.coder.commands.coder = coder

    @classmethod
    def create(
        cls,
        workspace_dir: str,
        files: list[str] | None = None,
        model: str | None = None,
        *,
        yes: bool = False,
        stream: bool = True,
        auto_commits: bool = True,
        dirty_commits: bool = True,
        dry_run: bool = False,
        map_tokens: int | None = None,
        on_event=None,
        echo_to_console: bool = False,
    ) -> Session:
        workspace = Path(workspace_dir).resolve()
        if not workspace.is_dir():
            raise FileNotFoundError(f"Workspace not found: {workspace}")

        from bright_vision_core.vision_runtime import configure_vision_runtime, purge_legacy_tag_caches

        configure_vision_runtime()
        purge_legacy_tag_caches(workspace)

        prev_cwd = os.getcwd()
        os.chdir(workspace)
        try:
            io = EventIO(yes=yes, pretty=False, on_event=on_event, echo_to_console=echo_to_console)
            model_name = model or models.DEFAULT_MODEL_NAME
            main_model = models.Model(model_name)
            if main_model.is_ollama():
                main_model._ensure_extra_params_dict()
                main_model.extra_params.setdefault("keep_alive", -1)

            fnames = [str(Path(f).resolve()) for f in (files or [])]

            repo = None
            try:
                repo = create_git_workspace(
                    io,
                    fnames if fnames else [str(workspace)],
                    str(workspace),
                    models=main_model.commit_message_models(),
                )
            except FileNotFoundError:
                pass

            if map_tokens is None:
                map_tokens = main_model.get_repo_map_tokens()

            commands = Commands(io, None)
            coder = run(
                Coder.create(
                    main_model=main_model,
                    io=io,
                    repo=repo,
                    fnames=fnames,
                    stream=stream and main_model.streaming,
                    auto_commits=auto_commits,
                    dirty_commits=dirty_commits,
                    dry_run=dry_run,
                    map_tokens=map_tokens,
                    commands=commands,
                    use_git=repo is not None,
                    args=default_headless_args(yes=yes),
                )
            )
            commands.coder = coder
            rebind_coder_loop_primitives(coder)
            return cls(coder, io)
        finally:
            os.chdir(prev_cwd)

    def run_message(
        self,
        message: str,
        *,
        preproc: bool = True,
        active_todo_id: str | None = None,
        inject_todo_spec: bool = False,
    ) -> Iterator[dict[str, Any]]:
        turn_todo_id: str | None = None
        user_text = message
        if active_todo_id:
            todos = WorkspaceTodos(self.coder.root)
            store = todos.load()
            item = todos.find(store, active_todo_id)
            if item:
                turn_todo_id = item.id
                if inject_todo_spec:
                    user_text = format_todo_context(item, store=store) + message

        self.io.emit("user_message", text=user_text)
        for event in self.io.drain_events():
            yield event
        assistant_text: list[str] = []

        try:
            emit_progress(self.io, label="Vision", message="Preparing workspace…")
            yield from _drain_io_events(self.io)

            for item in _run_blocking_with_sse_pulses(
                self.io,
                self.coder.init_before_message,
                label="Vision",
                message="Preparing workspace",
            ):
                if isinstance(item, dict):
                    yield item
            self.io.user_input(user_text)

            user_msg = user_text
            if preproc:
                emit_progress(self.io, label="Vision", message="Running slash commands…")
                yield from _drain_io_events(self.io)

                def _preproc() -> str | None:
                    rebind_coder_loop_primitives(self.coder)

                    async def _preproc_coro():
                        return await self.coder.preproc_user_input(user_text)

                    return run(_preproc_coro())

                for item in _run_blocking_with_sse_pulses(
                    self.io,
                    _preproc,
                    label="Vision",
                    message="Running slash commands",
                ):
                    if isinstance(item, dict):
                        yield item
                    else:
                        user_msg = item

            if user_msg is None:
                for event in self.io.drain_events():
                    yield event
                yield self.io.emit("done", assistant_text="")
                return

            for event in self.io.drain_events():
                yield event

            emit_progress(self.io, label="LLM", message="Waiting for Ollama…")
            for event in self.io.drain_events():
                yield event

            for piece in iterate_async_with_heartbeats(
                lambda: self.coder.send_message(user_msg),
                self.io,
                coder=self.coder,
                label="LLM",
                message="Waiting for Ollama",
            ):
                yield from _drain_io_events(self.io)
                if piece is HEARTBEAT_PULSE:
                    continue
                if piece:
                    assistant_text.append(piece)
                    yield self.io.emit("token", text=piece)

            for event in self.io.drain_events():
                yield event

            edited = _edited_files(self.coder)
            payload: dict[str, Any] = {
                "assistant_text": "".join(assistant_text),
                "edited_files": edited,
                **_done_commit_fields(self.coder),
            }

            if turn_todo_id:
                payload["active_todo_id"] = turn_todo_id
                links: list[str] = list(edited)
                last_hash = getattr(self.coder, "last_aider_commit_hash", None)
                if last_hash:
                    links.append(f"commit:{last_hash}")
                WorkspaceTodos(self.coder.root).append_links(links, todo_id=turn_todo_id)

            yield self.io.emit("done", **payload)
        except BaseException as err:
            if is_switch_coder_signal(err):
                for event in self.io.drain_events():
                    yield event
                yield self.io.emit("done", assistant_text="".join(assistant_text))
                return
            if isinstance(err, BrokenPipeError):
                yield self.io.emit("error", text=str(err))
                yield self.io.emit("done", assistant_text="".join(assistant_text), error=True)
                return
            if isinstance(err, Exception):
                yield self.io.emit("error", text=str(err))
                yield self.io.emit("done", assistant_text="".join(assistant_text), error=True)
                return
            raise

    def add_files(self, paths: list[str]) -> list[dict[str, Any]]:
        if not paths:
            return []

        workspace = Path(self.coder.root).resolve()
        quoted: list[str] = []
        for raw in paths:
            p = Path(raw)
            if not p.is_absolute():
                p = workspace / p
            p = p.resolve()
            if not p.is_file():
                self.io.tool_error(f"Not a file: {p}")
                continue
            try:
                rel = p.relative_to(workspace)
                quoted.append(shlex.quote(str(rel).replace("\\", "/")))
            except ValueError:
                quoted.append(shlex.quote(str(p)))

        if quoted:
            run_slash_command_sync(self.coder, "add", " ".join(quoted))

        return self.io.drain_events()

    def stage_uploaded_file(self, filename: str, content: bytes) -> Path:
        workspace = Path(self.coder.root).resolve()
        attach_dir = workspace / ".aider-vision" / "attachments"
        attach_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(filename).name or "upload"
        dest = attach_dir / safe_name
        stem = dest.stem
        suffix = dest.suffix
        n = 1
        while dest.exists():
            dest = attach_dir / f"{stem}-{n}{suffix}"
            n += 1
        dest.write_bytes(content)
        return dest

    def upload_files(self, items: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
        paths: list[str] = []
        for name, data in items:
            if len(data) > 20 * 1024 * 1024:
                self.io.tool_error(f"File too large (max 20MB): {name}")
                continue
            dest = self.stage_uploaded_file(name, data)
            paths.append(str(dest))
        return self.add_files(paths) if paths else self.io.drain_events()

    @staticmethod
    def decode_upload(content_base64: str) -> bytes:
        raw = content_base64.strip()
        if "," in raw and raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        return base64.b64decode(raw, validate=False)

    def undo(self) -> list[dict[str, Any]]:
        undo_last_aider_commit_for_coder(self.coder, self.io)
        return self.io.drain_events()

    def run_one_shot(self, message: str) -> str:
        parts: list[str] = []
        for event in self.run_message(message, preproc=False):
            if event.get("type") == "token":
                parts.append(str(event.get("text") or ""))
            elif event.get("type") == "done":
                return str(event.get("assistant_text") or "".join(parts))
        return "".join(parts)

    def generate_todo_layers(
        self,
        todo_id: str,
        prompt: str,
        *,
        mode: str = "generate",
        apply: bool = True,
    ) -> dict[str, Any]:
        api = WorkspaceTodos(self.coder.root)
        item = api.get(todo_id)
        msg = build_generate_message(prompt, mode=mode, item=item)  # type: ignore[arg-type]
        raw = self.run_one_shot(msg)
        layers = parse_generated_layers(raw)
        if apply and any(layers.values()):
            item, _ = api.update(
                todo_id,
                requirements=layers.get("requirements", ""),
                design=layers.get("design", ""),
                tasks_md=layers.get("tasks_md", ""),
            )
        return {
            "requirements": layers.get("requirements", ""),
            "design": layers.get("design", ""),
            "tasks_md": layers.get("tasks_md", ""),
            "raw": raw,
            "item": item,
        }
