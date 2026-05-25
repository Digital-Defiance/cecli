"""
LLM-assisted three-layer todo spec generation and parsing.
"""

from __future__ import annotations

import re
from typing import Literal

from bright_vision_core.workspace_todos import TodoItem

GenerateMode = Literal["generate", "refine"]

_SECTION_HEADERS = {
    "## requirements": "requirements",
    "## design": "design",
    "## implementation tasks": "tasks_md",
}

_GENERATE_TEMPLATE = """\
You are writing a spec-driven development plan for this repository. Do not edit any files.

Feature request:
{prompt}

{existing}

Respond with markdown only, using exactly these three level-2 headings (no other top-level structure):

## Requirements
Use EARS-style bullets: **WHEN** … **THE** system **SHALL** …

## Design
Overview, architecture, components, and data flow for this repo.

## Implementation tasks
Numbered checklist items, one per line, format:
- [ ] 1. Short title (depends: none)
- [ ] 2. Next step (depends: 1)
"""

_REFINE_TEMPLATE = """\
You are reviewing a spec-driven task for consistency. Do not edit any files.

Task title: {title}

## Requirements
{requirements}

## Design
{design}

## Implementation tasks
{tasks_md}

User note: {prompt}

Output an improved version with the same three ## headings. Fix contradictions between layers and align implementation tasks with requirements and design.
"""


def build_generate_message(
    prompt: str,
    *,
    mode: GenerateMode = "generate",
    item: TodoItem | None = None,
) -> str:
    if mode == "refine" and item:
        return _REFINE_TEMPLATE.format(
            title=item.title,
            requirements=item.requirements.strip() or "(empty)",
            design=item.design.strip() or "(empty)",
            tasks_md=item.tasks_md.strip() or "(empty)",
            prompt=prompt.strip() or "Review for consistency.",
        )
    existing = ""
    if item and (item.requirements or item.design or item.tasks_md):
        existing = (
            "Existing draft (improve and extend):\n"
            f"Requirements:\n{item.requirements}\n\n"
            f"Design:\n{item.design}\n\n"
            f"Implementation tasks:\n{item.tasks_md}\n"
        )
    return _GENERATE_TEMPLATE.format(prompt=prompt.strip(), existing=existing)


def parse_generated_layers(text: str) -> dict[str, str]:
    """Extract requirements, design, and tasks_md from model markdown."""
    sections: dict[str, list[str]] = {k: [] for k in ("requirements", "design", "tasks_md")}
    current: str | None = None

    for line in text.replace("\r\n", "\n").split("\n"):
        key = _SECTION_HEADERS.get(line.strip().lower())
        if key:
            current = key
            continue
        if current:
            sections[current].append(line)

    out = {k: "\n".join(v).strip() for k, v in sections.items()}
    if not any(out.values()):
        cleaned = _strip_fences(text)
        if cleaned:
            out["requirements"] = cleaned
    return out


def _strip_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", t, re.DOTALL | re.I)
    return m.group(1).strip() if m else t
