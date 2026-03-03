from enum import Enum


class HookType(Enum):
    """Enumeration of hook types."""

    START = "start"
    ON_MESSAGE = "on_message"
    END_MESSAGE = "end_message"
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    END = "end"


# Metadata structure templates for each hook type
METADATA_TEMPLATES = {
    HookType.START: {},
    HookType.END: {},
    HookType.ON_MESSAGE: {"timestamp": str},
    HookType.END_MESSAGE: {"timestamp": str},
    HookType.PRE_TOOL: {"tool_name": str, "arg_string": str},
    HookType.POST_TOOL: {"tool_name": str, "arg_string": str, "output": str},
}
