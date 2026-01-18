import hashlib
import json
from typing import Any, Dict, Optional, Tuple


def generate_message_hash(
    role: str,
    content: Optional[str] = None,
    tool_calls: Optional[list] = None,
    hash_key: Optional[Tuple[str, ...]] = None,
) -> str:
    """
    Generate deterministic hash for a message.

    Args:
        role: Message role (user, assistant, system)
        content: Message content
        tool_calls: List of tool calls
        hash_key: Custom hash key for message identification

    Returns:
        MD5 hash string
    """
    if hash_key:
        # Use custom hash key if provided
        key_data = "".join(str(item) for item in hash_key)
    else:
        # Default: hash based on role and content/tool_calls
        if tool_calls:
            # For tool calls, include them in the hash
            tool_calls_str = json.dumps(
                [tool_call.to_dict() for tool_call in tool_calls], sort_keys=True
            )
            key_data = f"{role}:{tool_calls_str}"
        else:
            key_data = f"{role}:{content or ''}"

    return hashlib.md5(key_data.encode("utf-8")).hexdigest()


def validate_message_dict(message_dict: Dict[str, Any]) -> bool:
    """
    Validate message dictionary structure.

    Args:
        message_dict: Message dictionary to validate

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(message_dict, dict):
        return False

    if "role" not in message_dict:
        return False

    # Must have either content or tool_calls
    if "content" not in message_dict and "tool_calls" not in message_dict:
        return False

    return True


def calculate_priority_offset(
    base_priority: int,
    offset: int = 0,
    max_offset: int = 100,
) -> int:
    """
    Calculate priority with offset for fine-grained ordering.

    Args:
        base_priority: Base priority value
        offset: Offset to add to base priority
        max_offset: Maximum allowed offset

    Returns:
        Adjusted priority value
    """
    offset = max(0, min(offset, max_offset))
    return base_priority + offset


def calculate_timestamp_offset(
    base_timestamp: int,
    offset_ns: int = 0,
    max_offset_ns: int = 1_000_000_000,  # 1 second
) -> int:
    """
    Calculate timestamp with offset for fine-grained ordering.

    Args:
        base_timestamp: Base timestamp in nanoseconds
        offset_ns: Offset in nanoseconds
        max_offset_ns: Maximum allowed offset in nanoseconds

    Returns:
        Adjusted timestamp
    """
    offset_ns = max(0, min(offset_ns, max_offset_ns))
    return base_timestamp + offset_ns


def format_diff_for_message(diff_text: str, file_path: str) -> str:
    """
    Format diff text for inclusion in a message.

    Args:
        diff_text: Unified diff text
        file_path: Path to the file

    Returns:
        Formatted diff message
    """
    return f"File {file_path} has changed:\n\n{diff_text}"


def truncate_content(content: str, max_length: int = 1000) -> str:
    """
    Truncate content to maximum length.

    Args:
        content: Content to truncate
        max_length: Maximum length

    Returns:
        Truncated content with ellipsis if needed
    """
    if len(content) <= max_length:
        return content

    # Try to truncate at a word boundary
    truncated = content[:max_length]
    last_space = truncated.rfind(" ")

    if last_space > max_length * 0.8:  # If we found a space in the last 20%
        truncated = truncated[:last_space]

    return truncated + "..."


def get_message_preview(message_dict: Dict[str, Any], max_length: int = 50) -> str:
    """
    Get a preview of message content for debugging.

    Args:
        message_dict: Message dictionary
        max_length: Maximum preview length

    Returns:
        Preview string
    """
    content = message_dict.get("content", "")
    if not content:
        tool_calls = message_dict.get("tool_calls")
        if tool_calls:
            return f"[Tool calls: {len(tool_calls)}]"
        return "[No content]"

    return str(content)[:max_length]
