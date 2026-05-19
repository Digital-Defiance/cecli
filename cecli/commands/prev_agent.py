from cecli.commands.utils.base_command import BaseCommand


class PrevAgentCommand(BaseCommand):
    NORM_NAME = "prev-agent"
    DESCRIPTION = "Switch to the previous agent (primary or sub-agent)."

    @classmethod
    async def execute(cls, io, coder, args, **kwargs):
        if not coder.tui or not coder.tui():
            io.tool_error("This command is only available in TUI mode.")
            return
        coder.tui().action_switch_prev_agent()
