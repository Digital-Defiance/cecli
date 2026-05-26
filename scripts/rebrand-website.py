#!/usr/bin/env python3
"""Rebrand bright_vision_core/website from aider-vision-core copy (Aider → Bright, cecli lineage)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "bright_vision_core" / "website"

# Longer phrases first to avoid partial replacements.
REPLACEMENTS: list[tuple[str, str]] = [
    ("Aider Vision Core", "BrightVision Core"),
    ("aider-vision-core-serve", "bright-vision-core-serve"),
    ("aider-vision-core", "bright-vision-core"),
    ("aider_vision_core", "bright_vision_core"),
    ("Aider Vision", "BrightVision"),
    ("aider-vision.digitaldefiance.org", "bright-vision.digitaldefiance.org"),
    ("aider-vision-black.svg", "bright-vision.svg"),
    ("Digital-Defiance/aider-vision", "Digital-Defiance/BrightVision"),
    ("aider-vision", "bright-vision"),
    ("vision-notice.md", "bright-vision-notice.md"),
    ("Upstream Aider", "Upstream Cecli"),
    ("upstream Aider", "upstream Cecli"),
    ("from Aider", "from Cecli"),
    ("the Aider engine", "the Cecli engine"),
    ("Aider engine", "Cecli engine"),
    ("shared Aider", "bundled Cecli"),
    ("Aider-AI/aider", "dwash96/cecli"),
    ("https://aider.chat/docs/", "https://cecli.dev/docs/"),
    ("https://aider.chat/", "https://cecli.dev/"),
    ("aider.chat", "cecli.dev"),
    ("binary `aider`", "binary `cecli`"),
    ("`aider`", "`cecli`"),
    ("Aider Discord", "Cecli Discord"),
    ("Aider blog", "Cecli changelog"),
    ("Headless Aider", "Headless Cecli"),
    ("fork of Aider", "biforkation (Aider → Cecli → BrightVision Core)"),
    ("maintained fork of", "biforkation of"),
    ("aider vision core", "brightvision core"),
]

TEXT_SUFFIXES = {
    ".md",
    ".html",
    ".yml",
    ".yaml",
    ".css",
    ".js",
    ".json",
    ".txt",
    ".xml",
    ".sh",
}


def rebrand_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    if not ROOT.is_dir():
        print(f"missing {ROOT}", file=sys.stderr)
        return 1
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ("CNAME", "Gemfile"):
            continue
        if rebrand_file(path):
            changed += 1
    print(f"rebranded {changed} files under {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
