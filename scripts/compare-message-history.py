#!/usr/bin/env python3
"""
Compare agent trajectory JSON files from .cecli/logs/messages/

Sorts them by timestamp and finds where one trajectory diverges
from the next by comparing parsed JSON messages message-by-message.

Usage:
    python scripts/compare-message-history.py
    python scripts/compare-message-history.py <directory>
    python scripts/compare-message-history.py file1.json file2.json
"""

import glob
import json
import os
import re
import sys

DEFAULT_DIR = os.path.join(".cecli", "logs", "messages")
CONTEXT_SIZE = 40  # chars on each side of divergence (80 total window)


def _get_timestamp(filepath: str) -> float:
    """Extract the timestamp from a message log filename."""
    basename = os.path.basename(filepath)
    match = re.match(r"message-(\d+(?:\.\d+)?)\.log", basename)
    if match:
        return float(match.group(1))
    return 0.0


def _load_messages(filepath: str) -> list[dict]:
    """Load and parse a JSON message file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"Warning: {filepath} does not contain a JSON array, skipping", file=sys.stderr)
        return []
    return data


def _serialize_message(msg: dict) -> str:
    """Serialize a message dict to a consistent JSON string for comparison."""
    return json.dumps(msg, indent=2, ensure_ascii=False, sort_keys=True)


def _compare_messages(msg_a: dict, msg_b: dict) -> tuple[int, int] | None:
    """
    Compare two message dicts by serializing to JSON strings.
    Returns (divergence_offset, total_diff_bytes) where they differ, or None if identical.
    total_diff_bytes is the number of characters in B after the divergence point
    (i.e. how much content is different/new).
    """
    str_a = _serialize_message(msg_a)
    str_b = _serialize_message(msg_b)
    for i, (ca, cb) in enumerate(zip(str_a, str_b)):
        if ca != cb:
            diff_bytes = len(str_b) - i
            return i, diff_bytes
    if len(str_a) != len(str_b):
        diff_bytes = len(str_b) - len(str_a)
        return min(len(str_a), len(str_b)), diff_bytes
    return None


def _get_context_snippet(text: str, pos: int, size: int = CONTEXT_SIZE) -> str:
    """Extract an ~80-char window (40 before, 40 after) around a position."""
    start = max(0, pos - size)
    end = min(len(text), pos + size)
    snippet = text[start:end]
    prefix = "" if start == 0 else "..."
    suffix = "" if end == len(text) else "..."
    return f"{prefix}{snippet}{suffix}"

    """Extract an ~80-char window (40 before, 40 after) around a position."""
    start = max(0, pos - size)
    end = min(len(text), pos + size)
    snippet = text[start:end]
    prefix = "" if start == 0 else "..."
    suffix = "" if end == len(text) else "..."
    return f"{prefix}{snippet}{suffix}"


def compare_files(file_a: str, file_b: str) -> dict | None:
    """
    Compare two message log files.
    Returns a dict with divergence info, or None if identical.
    """
    msgs_a = _load_messages(file_a)
    msgs_b = _load_messages(file_b)

    if msgs_a == msgs_b:
        return None

    # Pre-compute serialized messages for size calculations
    serialized_b = [_serialize_message(m) for m in msgs_b]

    # Compare message by message to find the first differing index
    for idx in range(max(len(msgs_a), len(msgs_b))):
        if idx >= len(msgs_a):
            # File A ran out of messages — divergence is at the start of B's extra message
            msg_b_str = serialized_b[idx]
            diff_total = len(msg_b_str) + sum(len(s) for s in serialized_b[idx + 1 :])
            return {
                "file_a": file_a,
                "file_b": file_b,
                "message_index": idx,
                "offset_in_message": 0,
                "diff_bytes_after": diff_total,
                "snippet": _get_context_snippet(msg_b_str, 0),
                "reason": (
                    f"File A has {len(msgs_a)} messages, File B has {len(msgs_b)} (extra message at index {idx})"
                ),
                "context_b": msg_b_str[:80],
            }
        if idx >= len(msgs_b):
            # File B ran out of messages — divergence is at start of A's extra message
            msg_a_str = _serialize_message(msgs_a[idx])
            return {
                "file_a": file_a,
                "file_b": file_b,
                "message_index": idx,
                "offset_in_message": 0,
                "diff_bytes_after": len(msg_a_str),
                "snippet": _get_context_snippet(msg_a_str, 0),
                "reason": (
                    f"File B has {len(msgs_b)} messages, File A has {len(msgs_a)} (extra message at index {idx})"
                ),
                "context_b": msg_a_str[:80],
            }

        # Compare this message's content
        result = _compare_messages(msgs_a[idx], msgs_b[idx])
        if result is not None:
            offset, _diff_bytes = result
            msg_b_str = serialized_b[idx]
            # Total diff = remaining of this message + all subsequent messages
            diff_total = (len(msg_b_str) - offset) + sum(len(s) for s in serialized_b[idx + 1 :])
            return {
                "file_a": file_a,
                "file_b": file_b,
                "message_index": idx,
                "offset_in_message": offset,
                "diff_bytes_after": diff_total,
                "snippet": _get_context_snippet(msg_b_str, offset),
                "reason": f"Messages at index {idx} differ",
                "context_b": _get_context_snippet(msg_b_str, offset, 60),
            }

    return None  # Shouldn't reach here


def _format_result(result: dict) -> str:
    """Format a divergence result as a readable string."""
    lines = []
    lines.append("─" * 80)
    lines.append(f"Divergence at message index {result['message_index']}")
    lines.append(f"  → Offset {result['offset_in_message']} chars into that message (serialized)")
    lines.append(f"  → ~{result['diff_bytes_after'] / 4} diff tokens after divergence")
    lines.append(f"  → {result['reason']}")
    lines.append(f"  → File A: {result['file_a']}")
    lines.append(f"  → File B: {result['file_b']}")
    lines.append("")
    lines.append("Context around divergence (from file B serialized):")
    lines.append(f"  {result['snippet']}")
    return "\n".join(lines)


def run_all_comparisons(directory: str | None = None) -> None:
    """Find all message files, sort by time, and compare adjacent pairs."""
    if directory is None:
        directory = DEFAULT_DIR

    pattern = os.path.join(directory, "message-*.log")
    files = sorted(glob.glob(pattern), key=_get_timestamp)

    if not files:
        print(f"No message files found in {directory}/")
        return

    print(f"Found {len(files)} message files in {directory}")

    has_output = False
    for i in range(len(files) - 1):
        file_a = files[i]
        file_b = files[i + 1]

        result = compare_files(file_a, file_b)
        if result is None:
            print(f"\n{file_a} vs {file_b}")
            print("  → Files are identical")
            continue

        has_output = True
        print(_format_result(result))

    if not has_output and len(files) >= 2:
        print("\nNo divergences found between any adjacent file pairs.")
    elif len(files) < 2:
        print(f"\nNeed at least 2 files to compare, found {len(files)}.")


def run_specific_comparison(file_a: str, file_b: str) -> None:
    """Compare two specific files."""
    for fp in (file_a, file_b):
        if not os.path.isfile(fp):
            print(f"Error: file not found: {fp}", file=sys.stderr)
            sys.exit(1)

    result = compare_files(file_a, file_b)
    if result is None:
        print(f"{file_a} and {file_b} are identical.")
    else:
        print(_format_result(result))


def main() -> None:
    args = sys.argv[1:]

    if not args:
        run_all_comparisons()
    elif args == ["--all"]:
        run_all_comparisons()
    elif len(args) == 1:
        path = args[0]
        if os.path.isdir(path):
            run_all_comparisons(path)
        elif os.path.isfile(path):
            print(
                "Error: expected a directory, got a file. Use two arguments to compare specific files.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(f"Error: path not found: {path}", file=sys.stderr)
            sys.exit(1)
    elif len(args) == 2:
        run_specific_comparison(args[0], args[1])
    else:
        print("Usage:", file=sys.stderr)
        print(
            f"  {sys.argv[0]}                    # Compare all files in default directory ({DEFAULT_DIR})",
            file=sys.stderr,
        )
        print(
            f"  {sys.argv[0]} <directory>         # Compare all files in the given directory",
            file=sys.stderr,
        )
        print(
            f"  {sys.argv[0]} file1.json file2.json  # Compare two specific files", file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
