from typing import List

from cecli.commands.utils.base_command import BaseCommand
from cecli.hooks.manager import HookManager


class RemoveHookCommand(BaseCommand):
    NORM_NAME = "remove-hook"
    DESCRIPTION = "Disable a specific hook by name"

    @classmethod
    async def execute(cls, io, coder, args, **kwargs):
        """Execute the remove-hook command with given parameters."""
        # Get hook name from args string
        if not args.strip():
            io.tool_error("Usage: /remove-hook <hook-name>")
            return 1

        hook_name = args.strip()

        # Check if hook exists
        hook_manager = HookManager()
        if not hook_manager.hook_exists(hook_name):
            io.tool_error(f"Error: Hook '{hook_name}' not found")
            return 1

        # Disable the hook
        success = hook_manager.disable_hook(hook_name)

        if success:
            io.tool_output(f"Hook '{hook_name}' disabled successfully")
            return 0
        else:
            io.tool_error(f"Error: Failed to disable hook '{hook_name}'")
            return 1

    @classmethod
    def get_completions(cls, io, coder, args) -> List[str]:
        """Get completion options for remove-hook command."""
        hook_manager = HookManager()
        all_hooks = hook_manager.get_all_hooks()

        # Get all hook names
        hook_names = []
        for hooks in all_hooks.values():
            for hook in hooks:
                hook_names.append(hook.name)

        # Filter based on current args
        current_arg = args.strip()
        if current_arg:
            return [name for name in hook_names if name.startswith(current_arg)]
        else:
            return hook_names

    @classmethod
    def get_help(cls) -> str:
        """Get help text for the remove-hook command."""
        help_text = super().get_help()
        help_text += "\nUsage:\n"
        help_text += "  /remove-hook <hook-name>  # Disable a specific hook\n"
        help_text += "\nExamples:\n"
        help_text += "  /remove-hook my_start_hook\n"
        help_text += "  /remove-hook check_commands\n"
        help_text += "\nThis command disables a hook without removing it from the registry.\n"
        help_text += "Use /load-hook to re-enable it later.\n"
        help_text += "Use /hooks to see all available hooks and their current state.\n"
        return help_text
