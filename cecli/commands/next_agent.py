from cecli.commands.utils.base_command import BaseCommand


class NextAgentCommand(BaseCommand):
    NORM_NAME = "next-agent"
    DESCRIPTION = "Switch to the next agent (primary or sub-agent)."

    @classmethod
    async def execute(cls, io, coder, args, **kwargs):
        if not coder.tui or not coder.tui():
            io.tool_error("This command is only available in TUI mode.")
            return
        coder.tui().action_switch_next_agent()
