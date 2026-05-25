#!/usr/bin/env python3
"""Second pass: cecli commands, .cecli config paths, doc renames (bright_vision_core/website)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "bright_vision_core" / "website"

# Order matters: longer / more specific first.
REPLACEMENTS: list[tuple[str, str]] = [
    ("Aider LLM Leaderboards", "Cecli LLM Leaderboards"),
    ("Aider's polyglot benchmark", "Cecli's polyglot benchmark"),
    ("Aider's refactoring benchmark", "Cecli's refactoring benchmark"),
    ("Aider's code editing benchmark", "Cecli's code editing benchmark"),
    ("Aider's code editing leaderboard", "Cecli's code editing leaderboard"),
    ("Aider's benchmark", "Cecli's benchmark"),
    ("Aider's new unified diff", "Cecli's new unified diff"),
    ("Aider's new unified diff", "Cecli's unified diff"),
    ("Aider's new editing format", "Cecli's unified diff edit format"),
    ("Aider's new \"laziness\"", "Cecli's laziness"),
    ("Aider's existing", "Cecli's existing"),
    ("Aider's previous benchmark", "Cecli's previous benchmark"),
    ("Aider's simple", "Cecli's simple"),
    ("aider's polyglot benchmark", "cecli's polyglot benchmark"),
    ("aider's benchmark", "cecli's benchmark"),
    ("aider's model settings", "cecli model settings"),
    ("aider's benchmark suite", "cecli's benchmark suite"),
    ("aider's original", "cecli's original"),
    ("aider's new", "cecli's new"),
    ("aider's existing", "cecli's existing"),
    (".aider.model.settings.yml", ".cecli.model.settings.yml"),
    (".aider.model.settings.yaml", ".cecli.model.settings.yaml"),
    (".aider.conf.yml", ".cecli.conf.yml"),
    (".aider.conf.yaml", ".cecli.conf.yaml"),
    ("/docs/config/aider_conf.html", "/docs/config/cecli_conf.html"),
    ("aider_conf.html", "cecli_conf.html"),
    ("aider_conf.md", "cecli_conf.md"),
    ("/docs/troubleshooting/aider-not-found.html", "/docs/troubleshooting/cecli-not-found.html"),
    ("aider-not-found.html", "cecli-not-found.html"),
    ("aider-not-found.md", "cecli-not-found.md"),
    ("python-m-aider.md", "python-m-cecli.md"),
    # Commands (after package names)
    ("bright-vision-core --model", "cecli --model"),
    ("bright-vision-core --list", "cecli --list"),
    ("bright-vision-core --message", "cecli --message"),
    ("python -m bright_vision_core", "python -m cecli"),
    ("installing aider using", "installing cecli using"),
    ("install aider using", "install cecli using"),
    ("install aider with", "install cecli with"),
    ("install aider,", "install bright-vision-core,"),
    ("Install aider", "Install bright-vision-core"),
    ("install aider", "pip install bright-vision-core"),
    ("First, install aider", "First, install bright-vision-core"),
    ("will install aider", "installs cecli (via bright-vision-core)"),
    ("These one-liners will install aider", "Upstream one-liners install cecli"),
    ("You can install aider with", "You can install bright-vision-core with"),
    ("working with aider and", "working with cecli and"),
    ("working with aider on", "working with cecli on"),
    ("use aider with", "use cecli with"),
    ("Start working with aider", "Start working with cecli"),
    ("run aider with", "run cecli with"),
    ("run Aider with", "run cecli with"),
    ("to run aider", "to run cecli"),
    ("Run Aider with", "Run cecli with"),
    ("run Aider ", "run cecli "),
    ("configure Aider to", "configure cecli to"),
    ("configure aider to", "configure cecli to"),
    ("attempting to use them with Aider", "attempting to use them with cecli"),
    ("Make sure you have access to these models in your AWS account before attempting to use them with cecli", "Make sure you have access to these models in your AWS account before using them with cecli"),
    ("If you installed with aider-install", "If you installed with uv tool"),
    ("aider-install", "uv tool install cecli-dev"),
    ("code with aider", "code with cecli"),
    ("coding with aider", "coding with cecli"),
    ("chat with aider", "chat with cecli"),
    ("when aider ", "when cecli "),
    ("when Aider ", "when Cecli "),
    ("because aider ", "because cecli "),
    ("because Aider ", "because Cecli "),
    ("if aider ", "if cecli "),
    ("if Aider ", "if Cecli "),
    ("that aider ", "that cecli "),
    ("that Aider ", "that Cecli "),
    ("so aider ", "so cecli "),
    ("and aider ", "and cecli "),
    ("Aider will ", "Cecli will "),
    ("aider will ", "cecli will "),
    ("Aider can ", "Cecli can "),
    ("aider can ", "cecli can "),
    ("Aider uses ", "Cecli uses "),
    ("aider uses ", "cecli uses "),
    ("Aider has ", "Cecli has "),
    ("aider has ", "cecli has "),
    ("Aider lets ", "Cecli lets "),
    ("aider lets ", "cecli lets "),
    ("Aider needs ", "Cecli needs "),
    ("aider needs ", "cecli needs "),
    ("Aider gives ", "Cecli gives "),
    ("aider gives ", "cecli gives "),
    ("Aider supports ", "Cecli supports "),
    ("aider supports ", "cecli supports "),
    ("Aider provides ", "Cecli provides "),
    ("aider provides ", "cecli provides "),
    ("Aider takes ", "Cecli takes "),
    ("Aider tells ", "Cecli tells "),
    ("Aider tries ", "Cecli tries "),
    ("Aider now ", "Cecli now "),
    ("Aider relies ", "Cecli relies "),
    ("Aider also ", "Cecli also "),
    ("Aider wants ", "Cecli wants "),
    ("Aider should ", "Cecli should "),
    ("Aider automatically ", "Cecli automatically "),
    ("Aider is configured", "Cecli is configured"),
    ("Aider excels", "Cecli excels"),
    ("Most of aider's", "Most of cecli's"),
    ("Most of Aider's", "Most of Cecli's"),
    ("How to configure aider", "How to configure cecli"),
    ("# Aider not found", "# cecli not found"),
    ("way to run aider", "way to run cecli"),
    ("run aider in", "run cecli in"),
    ("$ aider ", "$ cecli "),
    ("> aider:", "> cecli:"),
    ("`aider` command", "`cecli` command"),
    (" the `aider` ", " the `cecli` "),
    ("flows installs **Aider**", "installs **cecli**"),
    ("not **Aider**,", "not **cecli-only upstream**,"),
    ("description: How to configure aider", "description: How to configure cecli"),
    ("aider: Removed", "cecli: Removed"),
    ("with aider.", "with cecli."),
    ("with aider ", "with cecli "),
    ("using aider.", "using cecli."),
    ("using aider ", "using cecli "),
    ("using Aider ", "using Cecli "),
    ("incorporated into aider", "incorporated into cecli"),
    ("originally building aider", "originally building cecli"),
    ("building aider.", "building cecli."),
    ("Aider now asks", "Cecli asks"),
    ("Aider's [", "Cecli's ["),
    ("[Aider](https://github.com/dwash96/cecli)", "[Cecli](https://github.com/dwash96/cecli)"),
    ("parent: Aider LLM", "parent: Cecli LLM"),
    ("# Editing an asciinema cast file with aider", "# Editing an asciinema cast file with cecli"),
    ("aider hello.cast", "cecli hello.cast"),
    ("aider: ", "cecli: "),
    (" Aider ", " Cecli "),
    (" aider ", " cecli "),
    ("Aider,", "Cecli,"),
]

# Regex replacements for command lines
REGEX_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\baider\b(?!\-ce)(?!\-vision)"), "cecli"),
    (re.compile(r"\bAider\b(?!\s+Vision)"), "Cecli"),
]

SKIP_DIRS = {"vendor", ".jekyll-cache", "_site"}
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
    ".ps1",
    ".env",
}


def rebrand_text(text: str) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    for pattern, repl in REGEX_REPLACEMENTS:
        text = pattern.sub(repl, text)
    # Fix double-fixes
    text = text.replace("cecli-dev-dev", "cecli-dev")
    text = text.replace("pip install bright-vision-core using", "installing cecli using")
    text = text.replace("Cecli Vision", "Bright Vision")
    text = text.replace("bright-vision-core-serve", "bright-vision-core-serve")  # noop guard
    return text


def rebrand_file(path: Path) -> bool:
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    updated = rebrand_text(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def rename_paths() -> None:
    renames = [
        (ROOT / "docs/config/aider_conf.md", ROOT / "docs/config/cecli_conf.md"),
        (ROOT / "docs/troubleshooting/aider-not-found.md", ROOT / "docs/troubleshooting/cecli-not-found.md"),
        (ROOT / "_includes/python-m-aider.md", ROOT / "_includes/python-m-cecli.md"),
    ]
    for src, dst in renames:
        if src.is_file() and not dst.exists():
            src.rename(dst)
            print(f"renamed {src.relative_to(ROOT)} -> {dst.name}")


def patch_cecli_conf_header() -> None:
    path = ROOT / "docs/config/cecli_conf.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "Aider will look for a this file",
        "Cecli will look for this file",
    )
    path.write_text(text, encoding="utf-8")


def patch_cecli_not_found() -> None:
    path = ROOT / "docs/troubleshooting/cecli-not-found.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "python -m cecli" not in text:
        text = text.replace(
            "python -m cecli\n```",
            "```bash\npython -m cecli\n```",
        )
    text = text.replace(
        "[installing cecli using aider-install",
        "[installing cecli using uv",
    )
    path.write_text(text, encoding="utf-8")


def add_history_banner() -> None:
    path = ROOT / "HISTORY.md"
    if not path.is_file():
        return
    banner = (
        "{: .note }\n"
        "**Bright Vision Core** site changelog. Older entries refer to **Aider** / **Cecli** "
        "upstream names; current CLI is `cecli`, HTTP serve is `bright-vision-core-serve`.\n\n"
    )
    if "Bright Vision Core** site changelog" in path.read_text(encoding="utf-8")[:500]:
        return
    body = path.read_text(encoding="utf-8")
    if body.startswith("---"):
        end = body.find("---", 3)
        if end != -1:
            end += 3
            path.write_text(body[:end] + "\n\n" + banner + body[end:].lstrip(), encoding="utf-8")
            return
    path.write_text(banner + body, encoding="utf-8")


def main() -> int:
    if not ROOT.is_dir():
        print(f"missing {ROOT}", file=sys.stderr)
        return 1

    rename_paths()
    changed = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ("sample.env",):
            continue
        if rebrand_file(path):
            changed += 1

    patch_cecli_conf_header()
    patch_cecli_not_found()
    add_history_banner()

    # Fix get-started CLI
    gs = ROOT / "_includes/get-started.md"
    if gs.is_file():
        t = gs.read_text(encoding="utf-8")
        t = t.replace("bright-vision-core --model", "cecli --model")
        gs.write_text(t, encoding="utf-8")

    print(f"pass2: updated {changed} files under {ROOT}")
    remaining = 0
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".html"}:
            try:
                if re.search(r"\baider\b", path.read_text(encoding="utf-8"), re.I):
                    remaining += 1
            except OSError:
                pass
    print(f"files with 'aider' remaining (may be URLs/history): {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
