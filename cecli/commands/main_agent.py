from cecli.commands.utils.base_command import BaseCommand


class MainAgentCommand(BaseCommand):
    NORM_NAME = "main-agent"
    DESCRIPTION = "Switch to the main/primary agent."

    @classmethod
    async def execute(cls, io, coder, args, **kwargs):
        if not coder.tui or not coder.tui():
            io.tool_error("This command is only available in TUI mode.")
            return
        coder.tui().action_switch_to_primary()
