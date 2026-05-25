"""
Workspace task list persisted in ``.aider-vision/todos.json``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

TodoStatus = Literal["open", "in_progress", "done", "cancelled"]

TODO_TEMPLATES: dict[str, str] = {
    "feature": (
        "## Goal\n\n"
        "## Requirements\n\n"
        "## Acceptance criteria\n"
        "- [ ] \n"
    ),
    "bugfix": (
        "## Problem\n\n"
        "## Root cause\n\n"
        "## Fix verification\n"
        "- [ ] Repro fixed\n"
        "- [ ] Tests pass\n"
    ),
    "refactor": (
        "## Scope\n\n"
        "## Non-goals\n\n"
        "## Acceptance criteria\n"
        "- [ ] Behavior unchanged\n"
        "- [ ] \n"
    ),
}

# Kiro-style three-layer spec (v4)
SPEC_LAYER_TEMPLATES: dict[str, dict[str, str]] = {
    "spec-driven": {
        "requirements": (
            "### REQ-001\n"
            "**WHEN** the user …\n"
            "**THE** system **SHALL** …\n\n"
            "### REQ-002\n"
            "**WHEN** …\n"
            "**THE** system **SHALL** …\n"
        ),
        "design": (
            "## Overview\n\n"
            "## Architecture\n\n"
            "## Components\n\n"
            "## Data flow\n\n"
        ),
        "tasks_md": (
            "## Implementation tasks\n\n"
            "- [ ] 1. … (depends: none)\n"
            "- [ ] 2. … (depends: 1)\n"
        ),
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def apply_template(name: str) -> str:
    return TODO_TEMPLATES.get((name or "").strip().lower(), "")


def apply_layer_template(name: str) -> dict[str, str]:
    return dict(SPEC_LAYER_TEMPLATES.get((name or "").strip().lower(), {}))


def migrate_todo_layers(item: TodoItem) -> TodoItem:
    """Move legacy single ``spec`` into ``requirements`` when layers are empty."""
    if item.spec.strip() and not (
        item.requirements.strip() or item.design.strip() or item.tasks_md.strip()
    ):
        item.requirements = item.spec.strip()
    return item


@dataclass
class ChecklistItem:
    id: str
    text: str
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChecklistItem:
        return cls(
            id=str(raw.get("id") or uuid.uuid4().hex[:8]),
            text=str(raw.get("text") or ""),
            done=bool(raw.get("done")),
        )


@dataclass
class TodoItem:
    id: str
    title: str
    spec: str = ""
    requirements: str = ""
    design: str = ""
    tasks_md: str = ""
    depends_on: list[str] = field(default_factory=list)
    branch: str = ""
    pr_url: str = ""
    status: TodoStatus = "open"
    links: list[str] = field(default_factory=list)
    checklist: list[ChecklistItem] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["checklist"] = [c.to_dict() for c in self.checklist]
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TodoItem:
        checklist = [ChecklistItem.from_dict(c) for c in raw.get("checklist") or []]
        status = raw.get("status")
        valid = status if status in ("open", "in_progress", "done", "cancelled") else "open"
        deps = raw.get("depends_on") or raw.get("dependsOn") or []
        item = cls(
            id=str(raw.get("id") or uuid.uuid4().hex),
            title=str(raw.get("title") or "Untitled"),
            spec=str(raw.get("spec") or ""),
            requirements=str(raw.get("requirements") or ""),
            design=str(raw.get("design") or ""),
            tasks_md=str(raw.get("tasks_md") or raw.get("tasksMd") or ""),
            depends_on=[str(d) for d in deps if str(d).strip()],
            branch=str(raw.get("branch") or ""),
            pr_url=str(raw.get("pr_url") or raw.get("prUrl") or ""),
            status=valid,
            links=list(raw.get("links") or []),
            checklist=checklist,
            created_at=str(raw.get("created_at") or _now_iso()),
            updated_at=str(raw.get("updated_at") or _now_iso()),
        )
        return migrate_todo_layers(item)


@dataclass
class TodoStore:
    version: int = 1
    active_id: str | None = None
    todos: list[TodoItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "activeId": self.active_id,
            "todos": [t.to_dict() for t in self.todos],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TodoStore:
        items = [TodoItem.from_dict(t) for t in raw.get("todos") or []]
        active = raw.get("activeId") or raw.get("active_id")
        if active and not any(t.id == active for t in items):
            active = None
        return cls(version=int(raw.get("version") or 1), active_id=active, todos=items)


def checklist_all_done(item: TodoItem) -> bool:
    if not item.checklist:
        return False
    return all(c.text.strip() and c.done for c in item.checklist)


def _layer_or_placeholder(text: str, placeholder: str) -> str:
    return text.strip() or placeholder


def format_todo_context(item: TodoItem, *, store: TodoStore | None = None) -> str:
    item = migrate_todo_layers(item)
    lines = [f"[Active task: {item.title} · id {item.id[:8]}]", ""]
    if item.branch.strip():
        lines.append(f"**Git branch:** {item.branch.strip()}")
    if item.pr_url.strip():
        lines.append(f"**Pull request:** {item.pr_url.strip()}")
    if item.branch.strip() or item.pr_url.strip():
        lines.append("")
    if item.depends_on and store:
        pending = []
        for dep_id in item.depends_on:
            dep = next(
                (t for t in store.todos if t.id == dep_id or t.id.startswith(dep_id)),
                None,
            )
            if dep and dep.status != "done":
                pending.append(f"{dep.title} ({dep.id[:8]})")
        if pending:
            lines += ["**Blocked by:** " + ", ".join(pending), ""]
    lines += [
        "## Requirements",
        _layer_or_placeholder(item.requirements, "(No requirements yet.)"),
        "",
        "## Design",
        _layer_or_placeholder(item.design, "(No design yet.)"),
        "",
        "## Implementation tasks",
        _layer_or_placeholder(item.tasks_md, "(No implementation tasks yet.)"),
    ]
    if item.spec.strip() and item.spec.strip() != item.requirements.strip():
        lines += ["", "## Legacy specification", item.spec.strip()]
    if item.checklist:
        lines += ["", "## Checklist"]
        for entry in item.checklist:
            mark = "x" if entry.done else " "
            lines.append(f"- [{mark}] {entry.text}")
    lines += ["", "---", ""]
    return "\n".join(lines)


class WorkspaceTodos:
    def __init__(self, workspace_dir: str | Path):
        self.root = Path(workspace_dir).resolve()
        self.path = self.root / ".aider-vision" / "todos.json"
        self.specs_root = self.root / ".aider-vision" / "specs"

    def sync_spec_files(self, item: TodoItem) -> None:
        """Write three-layer markdown under ``.aider-vision/specs/{id}/`` for external editing."""
        item = migrate_todo_layers(item)
        folder = self.specs_root / item.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "requirements.md").write_text(item.requirements or "", encoding="utf-8")
        (folder / "design.md").write_text(item.design or "", encoding="utf-8")
        (folder / "tasks.md").write_text(item.tasks_md or "", encoding="utf-8")

    def import_spec_files(self, todo_id: str) -> TodoItem:
        """Load ``requirements.md`` / ``design.md`` / ``tasks.md`` from disk into the task."""
        item = self.get(todo_id)
        folder = self.specs_root / todo_id
        if not folder.is_dir():
            raise ValueError(f"No spec folder for task: {todo_id}")
        layers: dict[str, str] = {}
        for filename, key in (
            ("requirements.md", "requirements"),
            ("design.md", "design"),
            ("tasks.md", "tasks_md"),
        ):
            path = folder / filename
            if path.is_file():
                layers[key] = path.read_text(encoding="utf-8")
        if not layers:
            raise ValueError(f"Spec folder is empty: {folder}")
        item, _ = self.update(
            todo_id,
            requirements=layers.get("requirements", item.requirements),
            design=layers.get("design", item.design),
            tasks_md=layers.get("tasks_md", item.tasks_md),
        )
        return item

    def load(self) -> TodoStore:
        if not self.path.is_file():
            return TodoStore()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return TodoStore()
        if not isinstance(data, dict):
            return TodoStore()
        return TodoStore.from_dict(data)

    def save(self, store: TodoStore) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(store.to_dict(), indent=2, ensure_ascii=False)
        self.path.write_text(payload + "\n", encoding="utf-8")

    def find(self, store: TodoStore, token: str) -> TodoItem | None:
        token = token.strip()
        if not token:
            return None
        for item in store.todos:
            if item.id == token or item.id.startswith(token):
                return item
        lower = token.lower()
        for item in store.todos:
            if item.title.lower() == lower:
                return item
        return None

    def get(self, todo_id: str) -> TodoItem:
        store = self.load()
        item = self.find(store, todo_id)
        if not item:
            raise ValueError(f"Unknown task: {todo_id}")
        return item

    def add(self, title: str, spec: str = "", *, template: str | None = None) -> TodoItem:
        store = self.load()
        tkey = (template or "").strip().lower()
        layers = apply_layer_template(tkey)
        if layers:
            item = TodoItem(
                id=uuid.uuid4().hex,
                title=title.strip() or "Untitled",
                requirements=layers.get("requirements", ""),
                design=layers.get("design", ""),
                tasks_md=layers.get("tasks_md", ""),
            )
        else:
            body = spec.strip() or apply_template(tkey)
            item = TodoItem(id=uuid.uuid4().hex, title=title.strip() or "Untitled", spec=body)
            migrate_todo_layers(item)
        store.todos.insert(0, item)
        self.save(store)
        self.sync_spec_files(item)
        return item

    def update(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        spec: str | None = None,
        requirements: str | None = None,
        design: str | None = None,
        tasks_md: str | None = None,
        depends_on: list[str] | None = None,
        branch: str | None = None,
        pr_url: str | None = None,
        status: TodoStatus | None = None,
        links: list[str] | None = None,
        checklist: list[ChecklistItem] | None = None,
        auto_complete_checklist: bool = True,
    ) -> tuple[TodoItem, bool]:
        """Returns ``(item, auto_completed)``."""
        store = self.load()
        item = self.find(store, todo_id)
        if not item:
            raise ValueError(f"Unknown task: {todo_id}")
        auto_completed = False
        if title is not None:
            item.title = title.strip() or "Untitled"
        if spec is not None:
            item.spec = spec
        if requirements is not None:
            item.requirements = requirements
        if design is not None:
            item.design = design
        if tasks_md is not None:
            item.tasks_md = tasks_md
        if depends_on is not None:
            item.depends_on = [d.strip() for d in depends_on if str(d).strip()]
        if branch is not None:
            item.branch = branch.strip()
        if pr_url is not None:
            item.pr_url = pr_url.strip()
        if status is not None:
            item.status = status
        if links is not None:
            item.links = list(links)
        if checklist is not None:
            item.checklist = checklist
        if (
            auto_complete_checklist
            and checklist is not None
            and checklist_all_done(item)
            and item.status not in ("done", "cancelled")
        ):
            item.status = "done"
            auto_completed = True
            if store.active_id == item.id:
                store.active_id = None
        item.updated_at = _now_iso()
        if status == "done" and store.active_id == item.id:
            store.active_id = None
        migrate_todo_layers(item)
        self.save(store)
        self.sync_spec_files(item)
        return item, auto_completed

    def import_markdown(self, text: str, *, merge: bool = False) -> TodoStore:
        from bright_vision_core.todo_markdown import import_markdown

        store = import_markdown(text, self.load() if merge else None, merge=merge)
        for item in store.todos:
            migrate_todo_layers(item)
            self.sync_spec_files(item)
        self.save(store)
        return store

    def export_markdown(self) -> str:
        from bright_vision_core.todo_markdown import export_markdown

        return export_markdown(self.load())

    def move(self, todo_id: str, direction: str) -> TodoStore:
        """Move a task up/down in list order (``direction``: ``up`` | ``down``)."""
        store = self.load()
        idx = next((i for i, t in enumerate(store.todos) if t.id == todo_id), None)
        if idx is None:
            raise ValueError(f"Unknown task: {todo_id}")
        delta = -1 if direction == "up" else 1
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(store.todos):
            return store
        store.todos[idx], store.todos[new_idx] = store.todos[new_idx], store.todos[idx]
        self.save(store)
        return store

    def delete(self, todo_id: str) -> None:
        store = self.load()
        before = len(store.todos)
        store.todos = [t for t in store.todos if t.id != todo_id]
        if len(store.todos) == before:
            raise ValueError(f"Unknown task: {todo_id}")
        if store.active_id == todo_id:
            store.active_id = None
        self.save(store)

    def set_active(self, todo_id: str | None) -> TodoStore:
        store = self.load()
        if todo_id:
            item = self.find(store, todo_id)
            if not item:
                raise ValueError(f"Unknown task id: {todo_id}")
            store.active_id = item.id
            if item.status == "open":
                item.status = "in_progress"
                item.updated_at = _now_iso()
        else:
            store.active_id = None
        self.save(store)
        return store

    def mark_done(self, token: str) -> TodoItem:
        store = self.load()
        item = self.find(store, token)
        if not item:
            raise ValueError(f"Unknown task: {token}")
        item.status = "done"
        item.updated_at = _now_iso()
        if store.active_id == item.id:
            store.active_id = None
        self.save(store)
        return item

    def append_links(self, links: list[str], *, todo_id: str | None = None) -> None:
        if not links:
            return
        store = self.load()
        target = todo_id or store.active_id
        if not target:
            return
        item = self.find(store, target)
        if not item:
            return
        seen = set(item.links)
        for link in links:
            s = str(link).strip()
            if s and s not in seen:
                item.links.append(s)
                seen.add(s)
        item.updated_at = _now_iso()
        self.save(store)
