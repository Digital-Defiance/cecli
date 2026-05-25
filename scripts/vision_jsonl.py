#!/usr/bin/env python3
"""
JSONL worker for aider-vision: read requests on stdin, stream events on stdout.

Each input line is JSON. Supported types:

  {"type": "message", "content": "..."}
  {"type": "shutdown"}

Each output line is a JSON event from :class:`bright_vision_core.event_io.EventIO` and
:class:`bright_vision_core.session.Session`.

Example:

  echo '{"type":"message","content":"add a hello function"}' | \\
    python scripts/vision_jsonl.py /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python scripts/vision_jsonl.py` without install
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bright_vision_core.session import Session  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="aider-vision JSONL session worker")
    parser.add_argument("workspace", help="Path to git workspace root")
    parser.add_argument("--model", default=None, help="Model name (default: aider default)")
    parser.add_argument("--file", action="append", default=[], help="File to add to chat (repeatable)")
    parser.add_argument("--no-stream", action="store_true", help="Disable LLM streaming")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no file writes)")
    args = parser.parse_args()

    def on_event(event):
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    session = Session.create(
        args.workspace,
        files=args.file or None,
        model=args.model,
        stream=not args.no_stream,
        dry_run=args.dry_run,
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as err:
            on_event({"type": "error", "text": f"Invalid JSON: {err}"})
            continue

        req_type = req.get("type")
        if req_type == "shutdown":
            break
        if req_type != "message":
            on_event({"type": "error", "text": f"Unknown request type: {req_type}"})
            continue

        content = req.get("content") or req.get("text") or ""
        for event in session.run_message(content):
            on_event(event)


if __name__ == "__main__":
    main()
