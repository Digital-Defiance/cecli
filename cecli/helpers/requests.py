from ..sendchat import ensure_alternating_roles


def add_reasoning_content(messages):
    """Add empty reasoning content field to assistant messages if not present.

    Args:
        messages: List of message dictionaries

    Returns:
        List of messages with reasoning content added to assistant messages
    """
    for msg in messages:
        if msg.get("role") == "assistant" and "reasoning_content" not in msg:
            msg["reasoning_content"] = ""
    return messages


def remove_empty_tool_calls(messages):
    """Remove messages with tool_calls that are empty arrays.

    Args:
        messages: List of message dictionaries

    Returns:
        List of messages with empty tool_calls messages removed
    """
    return [
        msg
        for msg in messages
        if not (msg.get("role") == "assistant" and "tool_calls" in msg and msg["tool_calls"] == [])
    ]


def thought_signature(model, messages):
    # Add thought signatures for Vertex AI and Gemini models
    if model.name.startswith("vertex_ai/") or model.name.startswith("gemini/"):
        for msg in messages:
            if "tool_calls" in msg:
                tool_calls = msg["tool_calls"]

                if tool_calls:
                    for call in tool_calls:
                        if not call:
                            continue

                        # Check if thought signature is missing in extra_content.google.thought_signature
                        if "provider_specific_fields" not in call:
                            call["provider_specific_fields"] = {}
                        if "thought_signature" not in call["provider_specific_fields"]:
                            if "thought_signatures" in call["provider_specific_fields"] and len(
                                call["provider_specific_fields"]["thought_signatures"]
                            ):
                                call["provider_specific_fields"]["thought_signature"] = call[
                                    "provider_specific_fields"
                                ]["thought_signatures"][0]

                                call["provider_specific_fields"].pop("thought_signatures", None)
                            else:
                                call["provider_specific_fields"][
                                    "thought_signature"
                                ] = "skip_thought_signature_validator"

            if "function_call" in msg:
                call = msg["function_call"]

                if not call:
                    continue

                # Check if thought signature is missing in extra_content.google.thought_signature
                if "provider_specific_fields" not in call:
                    call["provider_specific_fields"] = {}
                if "thought_signature" not in call["provider_specific_fields"]:
                    call["provider_specific_fields"][
                        "thought_signature"
                    ] = "skip_thought_signature_validator"

    return messages


def concatenate_user_messages(messages):
    """Concatenate user messages at the end of the array separated by assistant "(empty response)" messages.

    This function works backwards from the end of the messages array, collecting
    user messages until it encounters an assistant message that is not "(empty response)",
    a tool message, or a system message. All collected user messages are concatenated
    into a single user message at the end, and the original user messages are removed.

    Args:
        messages: List of message dictionaries

    Returns:
        List of messages with concatenated user messages
    """
    if not messages:
        return messages

    # Work backwards from the end
    user_messages_to_concat = []
    i = len(messages) - 1

    while i >= 0:
        msg = messages[i]
        role = msg.get("role")
        content = msg.get("content", "")

        # If it's a user message, add it to the collection
        if role == "user":
            user_messages_to_concat.insert(0, content)  # Insert at beginning to maintain order
            i -= 1
            continue

        # If it's an assistant message with "(empty response)", skip it and continue backwards
        if role == "assistant" and content == "(empty response)":
            i -= 1
            continue

        # If we hit any other type of message (non-empty assistant, tool, system, etc.), stop
        break

    # If we collected any user messages to concatenate
    if user_messages_to_concat:
        # Remove the original user messages (and any skipped empty assistant messages)
        # by keeping only messages up to index i (inclusive)
        result = messages[: i + 1] if i >= 0 else []

        # Add the concatenated user message at the end
        concatenated_content = "\n".join(user_messages_to_concat)
        result.append({"role": "user", "content": concatenated_content})

        return result

    # No user messages to concatenate, return original
    return messages


def model_request_parser(model, messages):
    messages = thought_signature(model, messages)
    messages = remove_empty_tool_calls(messages)
    messages = ensure_alternating_roles(messages)
    messages = add_reasoning_content(messages)
    messages = concatenate_user_messages(messages)
    return messages
