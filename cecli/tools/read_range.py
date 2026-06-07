import os
from typing import Dict, List

from cecli.helpers.hashline import hashline, strip_hashline
from cecli.tools.utils.base_tool import BaseTool
from cecli.tools.utils.helpers import (
    ToolError,
    handle_tool_error,
    is_provided,
    resolve_paths,
)
from cecli.tools.utils.output import color_markers, tool_footer, tool_header
from cecli.tools.validations import ToolValidations


class Tool(BaseTool):
    NORM_NAME = "readrange"
    TRACK_INVOCATIONS = False
    VALIDATIONS = {
        "show": ["coerce_list"],
        "show[]": ["coerce_dict"],
        "show[].start_marker": ["coerce_str"],
        "show[].end_marker": ["coerce_str"],
    }
    SCHEMA = {
        "type": "function",
        "function": {
            "name": "ReadRange",
            "description": (
                "Get content hash prefixes of content between start and end markers in files."
                " This is useful for files you are attempting to edit and for understanding their structure."
                " Accepts an array of `show` objects, each with file_path, start_marker, end_marker."
                " These values should be lines of content in the file. They can contain up to 3"
                " lines of content but newlines should generally be avoided. Avoid using generic keywords and"
                " symbols. Special markers @000 and 000@ represent the file boundaries and can be"
                " used for start_marker and end_marker for the first and last lines of the file"
                " respectively. Line numbers may also be used for range lookups."
                " It is best to use function names, variable declarations and other meaningful identifiers"
                " as start_marker and end_marker values."
                " Do not use both of the special markers together on non-empty file."
                " Do not use content hashes as the start_marker and end_marker values."
                " Do not use the same pattern for the start_marker and end_marker."
                " Do not use empty strings for the start_marker and end_marker."
                " Prefer using this tool to cli tools for reading files."
                " Calling this tool sequentially on increasingly finer grained searchers "
                " will help with getting outlines of important structural features"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "show": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "File path to search in.",
                                },
                                "start_marker": {
                                    "type": "string",
                                    "description": (
                                        "The text marking the beginning of the range."
                                        " Use '@000' for the first line on empty files."
                                    ),
                                },
                                "end_marker": {
                                    "type": "string",
                                    "description": (
                                        "The text marking the end of the range."
                                        " Use '000@' for the last line on empty files."
                                    ),
                                },
                            },
                            "required": ["file_path", "start_marker", "end_marker"],
                        },
                        "description": "Array of show operations to perform.",
                    },
                },
                "required": ["show"],
            },
        },
    }

    _last_invocation = {}  # file_path -> {start_idx, end_idx}
    _last_read_turn: Dict[str, int] = {}  # abs_path -> turn_count when last read

    @classmethod
    def execute(cls, coder, show, **kwargs):
        """
        Displays numbered lines from multiple files centered around target locations
        (patterns or line_numbers), without adding files to context.
        Accepts an array of show operations to perform.
        Uses utility functions for path resolution and error handling.
        """
        from cecli.helpers.conversation import ConversationService

        tool_name = "ReadRange"
        already_up_to_date = []
        new_context_retrieved = []
        error_outputs = []

        try:
            # 1. Validate show parameter
            if not isinstance(show, list):
                show = [show] if isinstance(show, dict) else show

            if len(show) == 0:
                raise ToolError("show array cannot be empty")

            all_outputs = []
            already_up_to_details = []
            new_context_details = []
            ranges = {}

            for show_index, show_op in enumerate(show):
                # Extract parameters for this show operation
                file_path = show_op.get("file_path")
                start_marker = show_op.get("start_marker")
                end_marker = show_op.get("end_marker")
                padding = 5

                if file_path is None:
                    error_outputs.append(
                        cls.format_error(
                            coder,
                            f"Show operation {show_index + 1} missing required file_path parameter",
                            None,
                            None,
                            None,
                            show_index,
                        )
                    )
                    continue

                # Validate arguments for this operation
                if not is_provided(start_marker) or not is_provided(end_marker):
                    error_outputs.append(
                        cls.format_error(
                            coder,
                            (
                                f"Show operation {show_index + 1}: Provide both 'start_marker' and"
                                " 'end_marker'."
                            ),
                            file_path,
                            start_marker,
                            end_marker,
                            show_index,
                        )
                    )
                    continue

                if start_marker.count("\n") > 4 or end_marker.count("\n") > 4:
                    error_outputs.append(
                        cls.format_error(
                            coder,
                            "Patterns must not contain more than 5 lines.",
                            file_path,
                            start_marker,
                            end_marker,
                            show_index,
                        )
                    )
                    continue

                start_marker = strip_hashline(start_marker).strip()
                end_marker = strip_hashline(end_marker).strip()

                # 2. Resolve path
                abs_path, rel_path = resolve_paths(coder, file_path)
                if not os.path.exists(abs_path):
                    # Check existence after resolving, as resolve_paths doesn't guarantee existence
                    error_outputs.append(
                        cls.format_error(
                            coder,
                            f"File not found: {file_path}",
                            file_path,
                            start_marker,
                            end_marker,
                            show_index,
                        )
                    )
                    continue

                # 3. Read file content
                content = coder.io.read_text(abs_path)
                if content is None:
                    error_outputs.append(
                        cls.format_error(
                            coder,
                            f"Could not read file: {file_path}",
                            file_path,
                            start_marker,
                            end_marker,
                            show_index,
                        )
                    )
                    continue

                lines = content.splitlines()
                num_lines = len(lines)

                if num_lines == 0:
                    new_context_details.append(
                        "\n".join(
                            [
                                f"File {rel_path} is empty.",
                                (
                                    "Next: use EditText with start_line @000 and end_line @000 to"
                                    " write content, or ContextManager to scaffold — do not call"
                                    " ReadRange again on this empty file."
                                ),
                            ]
                        )
                    )
                    new_context_retrieved.append(rel_path)
                    cls._last_read_turn[abs_path] = coder.turn_count
                    continue
                # 4. Determine line range
                start_line_idx = -1
                end_line_idx = -1
                both_structured = False
                # found_by = ""

                if start_marker is not None and end_marker is not None:

                    def _is_valid_int(s):
                        try:
                            int(s)
                            return True
                        except ValueError:
                            return False

                    start_is_digit = _is_valid_int(start_marker)
                    end_is_digit = _is_valid_int(end_marker)
                    start_is_special = start_marker in ("@000", "000@")
                    end_is_special = end_marker in ("@000", "000@")
                    both_structured = (start_is_digit or start_is_special) and (
                        end_is_digit or end_is_special
                    )
                    start_is_text = not start_is_digit and not start_is_special
                    end_is_text = not end_is_digit and not end_is_special
                    mixed_special_search = (start_is_special and end_is_text) or (
                        end_is_special and start_is_text
                    )
                    start_indices = []
                    end_indices = []

                    if both_structured:
                        if start_is_digit:
                            start_line_num = int(start_marker)
                            start_line_num = max(1, min(start_line_num, num_lines))
                            start_indices = [start_line_num - 1]
                        else:
                            start_indices = [0]

                        if end_is_digit:
                            end_line_num = int(end_marker)
                            end_line_num = max(1, min(end_line_num, num_lines))
                            end_indices = [end_line_num - 1]
                        else:
                            end_indices = [num_lines - 1]
                    elif mixed_special_search:
                        if start_is_special:
                            # Start is special marker, end is text pattern
                            if start_marker == "@000":
                                start_indices = [0]
                            else:  # 000@
                                start_indices = [num_lines - 1]
                            # Search for end pattern as text
                            end_pattern_lines = end_marker.split("\n")
                            end_indices = []
                            for i in range(len(lines) - len(end_pattern_lines) + 1):
                                if all(
                                    p_line in lines[i + j]
                                    for j, p_line in enumerate(end_pattern_lines)
                                ):
                                    end_indices.append(i + len(end_pattern_lines) - 1)
                        else:
                            # Start is text pattern, end is special marker
                            start_pattern_lines = start_marker.split("\n")
                            start_indices = []
                            for i in range(len(lines) - len(start_pattern_lines) + 1):
                                if all(
                                    p_line in lines[i + j]
                                    for j, p_line in enumerate(start_pattern_lines)
                                ):
                                    start_indices.append(i)
                            if end_marker == "@000":
                                end_indices = [0]
                            else:  # 000@
                                end_indices = [num_lines - 1]
                    else:
                        start_pattern_lines = start_marker.split("\n")
                        start_indices = []
                        for i in range(len(lines) - len(start_pattern_lines) + 1):
                            if all(
                                p_line in lines[i + j]
                                for j, p_line in enumerate(start_pattern_lines)
                            ):
                                start_indices.append(i)

                        end_pattern_lines = end_marker.split("\n")
                        end_indices = []
                        for i in range(len(lines) - len(end_pattern_lines) + 1):
                            if all(
                                p_line in lines[i + j] for j, p_line in enumerate(end_pattern_lines)
                            ):
                                # For multiline end patterns, we want the index of the LAST line of the match
                                end_indices.append(i + len(end_pattern_lines) - 1)

                    if len(start_indices) > 5:
                        # Too many matches - use _last_invocation to disambiguate
                        last = cls._last_invocation.get(abs_path)
                        if last is None:
                            error_outputs.append(
                                cls.format_error(
                                    coder,
                                    (
                                        f"Start pattern '{start_marker}' too broad."
                                        " Refine your search. Be more specific."
                                    ),
                                    file_path,
                                    start_marker,
                                    end_marker,
                                    show_index,
                                )
                            )
                            continue

                        # Find the best match: smallest sum of absolute distances to last start/end
                        # that comes after the range, with tie-breaking by smallest sum
                        last_s, last_e = last["start_idx"], last["end_idx"]
                        candidates = []
                        for s in start_indices:
                            for e in [idx for idx in end_indices if idx >= s]:
                                dist_sum = abs(s - last_s) + abs(e - last_e)
                                candidates.append((dist_sum, s, e))
                        # Sort by distance sum, then prefer ranges after the last range
                        candidates.sort(key=lambda x: (x[0], x[1] < last_s, x[1], x[2]))
                        if candidates:
                            best_pair = (candidates[0][1], candidates[0][2])
                        else:
                            best_pair = None
                    else:
                        best_pair = None
                        min_dist = float("inf")

                        for s in start_indices:
                            for e in [idx for idx in end_indices if idx >= s]:
                                dist = e - s
                                if dist < min_dist:
                                    min_dist = dist
                                    best_pair = (s, e)

                        # If no valid pair found and one side has exactly one match,
                        # try inverted matching in case LLM got the order of methods wrong
                        if best_pair is None and (len(start_indices) == 1 or len(end_indices) == 1):
                            for s in start_indices:
                                for e in end_indices:
                                    if e < s:  # end pattern match is before start pattern match
                                        dist = s - e
                                        if dist < min_dist:
                                            min_dist = dist
                                            best_pair = (e, s)

                        if not start_indices:
                            error_outputs.append(
                                cls.format_error(
                                    coder,
                                    (
                                        f"Start pattern '{start_marker}' not found in {file_path}."
                                        " Refine your search."
                                    ),
                                    file_path,
                                    start_marker,
                                    end_marker,
                                    show_index,
                                )
                            )
                            continue

                        if not end_indices:
                            error_outputs.append(
                                cls.format_error(
                                    coder,
                                    (
                                        f"End pattern '{end_marker}' not found in {file_path}."
                                        " Refine your search."
                                    ),
                                    file_path,
                                    start_marker,
                                    end_marker,
                                    show_index,
                                )
                            )
                            continue

                        if best_pair is None:
                            error_outputs.append(
                                cls.format_error(
                                    coder,
                                    (
                                        f"End pattern '{end_marker}' not found after start pattern in"
                                        f" {file_path}."
                                    ),
                                    file_path,
                                    start_marker,
                                    end_marker,
                                    show_index,
                                )
                            )
                            continue

                    s_idx, e_idx = best_pair

                # For structured searches (line numbers, special markers) or mixed searches
                # (one special marker, one text pattern), cap large ranges with preview
                # Text pattern searches are not subject to capping
                if (both_structured or mixed_special_search) and (e_idx - s_idx > 200):
                    preview = cls._get_range_preview(
                        abs_path, coder.io, start_idx=s_idx, end_idx=e_idx, line_numbers=True
                    )
                    if show_index > 0:
                        all_outputs.append("")
                    all_outputs.append(preview)
                    cls._last_invocation[abs_path] = {"start_idx": s_idx, "end_idx": e_idx}
                    continue

                # Store the found indices for future disambiguation
                cls._last_invocation[abs_path] = {"start_idx": s_idx, "end_idx": e_idx}

                # found_by = f"range '{start_marker}' to '{end_marker}'"

                try:
                    padding_int = int(padding)
                    if padding_int < 0:
                        raise ValueError()
                except ValueError:
                    coder.io.tool_warning(f"Invalid padding '{padding}', using default 5.")
                    padding_int = 5

                start_line_idx = max(0, s_idx - padding_int)
                end_line_idx = min(num_lines - 1, e_idx + padding_int)
                if start_line_idx == -1 or end_line_idx == -1:
                    error_outputs.append(
                        cls.format_error(
                            coder,
                            "Internal error: Could not determine line range.",
                            file_path,
                            start_marker,
                            end_marker,
                            show_index,
                        )
                    )
                    continue

                # 6. Format output for this operation
                # Use rel_path for user-facing messages
                # output_lines = [f"Displaying context around {found_by} in {rel_path}:"]

                # Generate hashline for the entire file
                hashed_content = hashline(content)
                hashed_lines = hashed_content.splitlines()

                # Extract the context window from hashed lines
                # context_hashed_lines = hashed_lines[start_line_idx : end_line_idx + 1]

                # for i in range(start_line_idx, end_line_idx + 1):
                #    hashed_line = context_hashed_lines[i - start_line_idx]
                #    output_lines.append(hashed_line)

                # Add separator between multiple show operations
                # if show_index > 0:
                #     all_outputs.append("")
                # all_outputs.extend(output_lines)

                # Update the conversation cache with the displayed range
                # Note: start_line_idx and end_line_idx are 0-based, convert to 1-based for hashline
                start_line = start_line_idx + 1  # Convert to 1-based
                end_line = end_line_idx + 1  # Convert to 1-based

                original_context_content = ConversationService.get_files(coder).get_file_context(
                    abs_path,
                    all_ranges=True,
                )
                update_tuple = ConversationService.get_files(coder).update_file_context(
                    abs_path, start_line, end_line, auto_remove=False
                )
                new_context_content = ConversationService.get_files(coder).get_file_context(
                    abs_path,
                    all_ranges=True,
                )

                is_already_up_to_date = False
                add_to_ranges = False
                last_turn = cls._last_read_turn.get(abs_path)

                if original_context_content and original_context_content == new_context_content:
                    already_up_to_date.append(rel_path)
                    is_already_up_to_date = True

                    if last_turn is None or coder.turn_count - last_turn < 3 and already_up_to_date:
                        add_to_ranges = True
                else:
                    add_to_ranges = True

                if add_to_ranges:
                    if not ranges.get(abs_path, None):
                        ranges[abs_path] = []

                    ranges[abs_path].append(update_tuple)

                    if not is_already_up_to_date:
                        new_context_retrieved.append(rel_path)

                # Collect hashline info for response
                if (
                    s_idx >= 0
                    and s_idx < len(hashed_lines)
                    and e_idx >= 0
                    and e_idx < len(hashed_lines)
                ):
                    hashed_slice = hashed_lines[s_idx : e_idx + 1]
                    if is_already_up_to_date:
                        already_up_to_details.append(
                            cls.format_model_response(coder, rel_path, s_idx, e_idx, hashed_slice)
                        )
                    else:
                        new_context_details.append(
                            cls.format_model_response(coder, rel_path, s_idx, e_idx, hashed_slice)
                        )

                # Conditionally remove old file context messages
                # If the file was last read >= 3 turns ago, keep old messages (allow coexistence)
                # Otherwise, remove them to avoid duplicates

                # last_turn = cls._last_read_turn.get(abs_path)
                # if last_turn is None or coder.turn_count - last_turn < 3 and already_up_to_date:
                #    ConversationService.get_files(coder).remove_file_messages(abs_path)

                # Update the last read turn for this file
                cls._last_read_turn[abs_path] = coder.turn_count

            for abs_path, tuples in ranges.items():
                ConversationService.get_files(coder).clear_ranges(abs_path)
                ConversationService.get_files(coder).push_range(abs_path, tuples)

            ConversationService.get_chunks(coder).add_file_context_messages()
            cls.clear_old_messages(coder)

            # Log success and return the formatted context directly
            coder.edit_allowed = True

            result_parts = [f"File Context Turn {coder.turn_count}"]

            if already_up_to_details or new_context_details:
                if new_context_details:
                    coder.io.tool_output(
                        f"✅ Retrieved context for {len(new_context_details)} operation(s)"
                    )

                    detail_str = "\n".join(new_context_details)
                    result_parts.append(
                        f"Retrieved context for {len(new_context_details)} operation(s):\n\n"
                        f"{detail_str}\n"
                    )
                if already_up_to_details:
                    coder.io.tool_output(
                        "Lines already up to date in context for"
                        f" {len(already_up_to_details)} operation(s)"
                    )

                    detail_str = "\n".join(already_up_to_details)
                    result_parts.append(
                        "Content up to date and available in history from previous read for "
                        f"{len(already_up_to_details)} operation(s):\n\n"
                        f"{detail_str}\n"
                    )
                if already_up_to_date and not new_context_retrieved:
                    result_parts.append(
                        "Do not call `ReadRange` again with these parameters again unless you edit"
                        " the relevant files."
                    )

            if all_outputs:
                result_parts.append("\n".join(all_outputs))

            if error_outputs:
                coder.io.tool_error(f"Errors encountered for {len(error_outputs)} operation(s)")

                result_parts.append("Errors:\n" + "\n".join(error_outputs))

            if not result_parts:
                return "No files could be processed."

            return "\n---\n".join(result_parts)

        except ToolError as e:
            # Handle expected errors raised by utility functions or validation
            return handle_tool_error(coder, tool_name, e, add_traceback=False)
        except Exception as e:
            # Handle unexpected errors during processing
            return handle_tool_error(coder, tool_name, e)

    @classmethod
    def format_model_response(cls, coder, rel_path, s_idx, e_idx, hashed_slice):
        """Format a file's context range as hash-prefixed lines for the model."""
        lines = [f"File {rel_path} Snapshot (Lines {s_idx + 1} - {e_idx + 1}):"]
        total = len(hashed_slice)
        if total <= 10:
            lines.extend(hashed_slice)
        else:
            lines.extend(hashed_slice[:5])
            lines.append("...")
            lines.extend(hashed_slice[-5:])
        lines.append("")
        return "\n".join(lines)

    @classmethod
    def clear_old_messages(cls, coder):
        from cecli.helpers.conversation import ConversationService, MessageTag

        # Clean up stale file_context messages
        # If a file has 5 or more file_context_user messages, remove all but the most recent
        # (and their corresponding assistant messages) to prevent excessive stale context
        file_context_messages = ConversationService.get_manager(coder).get_tag_messages(
            MessageTag.FILE_CONTEXTS
        )
        # Only process the latest 3rd of messages to leave older context alone
        breakpoint = len(file_context_messages) * 2 // 3
        file_context_messages = file_context_messages[breakpoint:]

        # Group user file_context messages by file path
        user_msgs_by_file: Dict[str, List[int]] = {}
        user_msg_indices: List[int] = []
        for msg_idx, msg in enumerate(file_context_messages):
            if msg.hash_key and len(msg.hash_key) == 3 and msg.hash_key[0] == "file_context_user":
                file_path = msg.hash_key[1]
                if file_path not in user_msgs_by_file:
                    user_msgs_by_file[file_path] = []
                user_msgs_by_file[file_path].append(msg_idx)
                user_msg_indices.append(msg_idx)

        # If any file has 5+ user messages, shave all files to latest single context message
        # This prevents repeated cleanup cycles from staggered message accumulation
        hash_keys_to_remove: set = set()
        has_overflow = any(len(indices) >= 5 for indices in user_msgs_by_file.values())

        if has_overflow:
            for file_path, indices in user_msgs_by_file.items():
                # Keep only the latest message for each file
                older_indices = indices[:-1]
                for old_idx in older_indices:
                    old_msg = file_context_messages[old_idx]
                    content_hash = old_msg.hash_key[2]
                    # Mark the user message for removal
                    hash_keys_to_remove.add(("file_context_user", file_path, content_hash))
                    # Mark the corresponding assistant message for removal
                    hash_keys_to_remove.add(("file_context_assistant", file_path, content_hash))

        if hash_keys_to_remove:
            ConversationService.get_manager(coder).remove_messages_by_hash_key_pattern(
                lambda hash_key: hash_key in hash_keys_to_remove
            )

    @classmethod
    def format_output(cls, coder, mcp_server, tool_response):
        """Format output for ReadRange tool."""
        color_start, color_end = color_markers(coder)

        # Output header
        tool_header(coder=coder, mcp_server=mcp_server, tool_response=tool_response)

        try:
            params = ToolValidations.validate_params(
                tool_response.function.arguments, cls.VALIDATIONS, cls.SCHEMA
            )
        except ToolError:
            coder.io.tool_error("Invalid Tool JSON")
            return

        show_ops = params.get("show", [])
        if show_ops:
            coder.io.tool_output("")
            for i, show_op in enumerate(show_ops):
                file_path = show_op.get("file_path", "")
                start_marker = strip_hashline(show_op.get("start_marker", "")).strip()
                end_marker = strip_hashline(show_op.get("end_marker", "")).strip()

                # Format as "show: • file_path • start_marker • end_marker • padding"
                formatted_query = (
                    f"{color_start}range_{i + 1}:{color_end} {file_path} • {start_marker} •"
                    f" {end_marker}"
                )
                coder.io.tool_output(formatted_query)
            coder.io.tool_output("")

        tool_footer(coder=coder, tool_response=tool_response, params=params)

    @classmethod
    def format_error(cls, coder, error_text, file_path, start_marker, end_marker, operation_index):
        """Format error output for the ReadRange tool."""

        # Truncate start_marker to first line with ellipsis if multiline
        start_line = (start_marker or "N/A").split("\n")[0]
        if start_marker and start_marker.count("\n") > 0:
            start_line = start_line + " ..."

        # Truncate end_marker to first line with ellipsis if multiline
        end_line = (end_marker or "N/A").split("\n")[0]
        if end_marker and end_marker.count("\n") > 0:
            end_line = end_line + " ..."

        output = [
            f"[Operation {operation_index + 1}]",
            f"file_path: {file_path or 'N/A'}",
            f"start_marker: {start_line}",
            f"end_marker: {end_line}",
            "",
            error_text,
        ]

        return "\n".join(output)

    @classmethod
    def on_duplicate_request(cls, coder, **kwargs):
        coder.edit_allowed = True

    @classmethod
    def _get_range_preview(cls, abs_path, io, start_idx, end_idx, line_numbers=True):
        """Get a preview of a large file range between start_idx and end_idx.

        For code files (where tree-sitter can parse structure), uses
        RepoMap.get_file_stub to generate a structural outline. For non-code files
        (text, logs, markdown, etc.) where get_file_stub returns nothing useful,
        falls back to 20 equally-spaced lines from the range.

        Args:
            abs_path (str): Absolute path to the file
            io (InputOutput): Instance for file operations
            start_idx (int): 0-based start line of the range
            end_idx (int): 0-based end line of the range (inclusive)
            line_numbers (bool): Whether to include line numbers in output

        Returns:
            str: Formatted preview — structural outline for code, sampled lines for text
        """
        from cecli.repomap import RepoMap

        stub = RepoMap.get_file_stub(
            abs_path, io, start_line=start_idx, end_line=end_idx, line_numbers=line_numbers
        )

        # If get_file_stub returned a useful structural outline, wrap it with headers
        if stub and stub != "# No outline available":
            total_lines = end_idx - start_idx + 1
            parts = [
                f"File range too large ({total_lines} lines).",
                "Showing structural outline of the range:",
                "",
                stub,
            ]
            return "\n".join(parts)

        content = io.read_text(abs_path)
        if not content:
            return ""

        lines = content.splitlines()
        num_file_lines = len(lines)
        # Clamp indices to actual file content bounds
        actual_start = max(0, min(start_idx, num_file_lines - 1))
        actual_end = max(0, min(end_idx, num_file_lines - 1))
        total_lines = actual_end - actual_start + 1

        if total_lines <= 0:
            return ""

        if total_lines <= 20:
            # Return all lines
            sample_lines = [(actual_start + i, lines[actual_start + i]) for i in range(total_lines)]
        else:
            # Pick 20 equally-spaced lines across the range
            spacing = max(1, total_lines // 20)
            sample_lines = []
            for i in range(0, total_lines, spacing):
                if len(sample_lines) >= 20:
                    break
                idx = actual_start + i
                # Deduplicate sequential indices from uneven spacing
                if not sample_lines or idx != sample_lines[-1][0]:
                    sample_lines.append((idx, lines[idx]))

            # Always include the last line
            if sample_lines and sample_lines[-1][0] != actual_end:
                sample_lines.append((actual_end, lines[actual_end]))

        # Format the output
        parts = [
            f"File range too large ({total_lines} lines).",
            f"Showing {len(sample_lines)} equally-spaced lines from the range:",
            "",
        ]
        for idx, line_content in sample_lines:
            line_num = idx + 1
            parts.append(f"  {line_num:>5} | {line_content}")

        return "\n".join(parts)
