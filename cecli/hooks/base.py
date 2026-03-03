import asyncio
import shlex
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from cecli.run_cmd import run_cmd

from .types import HookType


class BaseHook(ABC):
    """Base class for all hooks."""

    type: HookType
    name: str
    priority: int = 10
    enabled: bool = True
    description: Optional[str] = None

    def __init__(self, name: Optional[str] = None, priority: int = 10, enabled: bool = True):
        """Initialize a hook.

        Args:
            name: Optional name for the hook. If not provided, uses class name.
            priority: Hook priority (lower = higher priority). Default is 10.
            enabled: Whether the hook is enabled. Default is True.
        """
        self.name = name or self.__class__.__name__
        self.priority = priority
        self.enabled = enabled

        # Validate that subclass has defined type
        if not hasattr(self, "type") or self.type is None:
            raise ValueError(f"Hook {self.__class__.__name__} must define a 'type' attribute")

    @abstractmethod
    async def execute(self, coder: Any, metadata: Dict[str, Any]) -> Any:
        """Execute the hook logic.

        Args:
            coder: The coder instance providing context.
            metadata: Dictionary with metadata about the current operation.

        Returns:
            Any value. For Python hooks, return False or falsy value to abort operation.
            For command hooks, non-zero exit code aborts operation.
        """
        pass

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name='{self.name}', type={self.type},"
            f" priority={self.priority}, enabled={self.enabled})"
        )


class CommandHook(BaseHook):
    """Hook that executes a command-line script."""

    command: str

    def __init__(self, command: str, hook_type: str, **kwargs):
        """Initialize a command hook.

        Args:
            command: The command to execute.
            **kwargs: Additional arguments passed to BaseHook.
        """
        self.type = hook_type
        super().__init__(**kwargs)
        self.command = command

    async def execute(self, coder: Any, metadata: Dict[str, Any]) -> Any:
        """Execute the command hook.

        Args:
            coder: The coder instance providing context.
            metadata: Dictionary with metadata about the current operation.

        Returns:
            Exit code of the command. Non-zero exit code aborts operation.
        """
        import subprocess

        # Escape metadata values for shell safety
        safe_metadata = {k: shlex.quote(str(v)) for k, v in metadata.items()}

        # Format command with metadata
        formatted_command = self.command.format(**safe_metadata)

        try:
            exit_status, result = await asyncio.to_thread(
                run_cmd, formatted_command, error_print=coder.io.tool_error, cwd=coder.root
            )

            printed_result = ""

            if result:
                printed_result = f" result: {result}"

            if coder.verbose or exit_status != 0:
                print(f"[Hook {self.name}]{printed_result}")

            return exit_status

        except subprocess.TimeoutExpired:
            print(f"[Hook {self.name}] Timeout")
            return 1  # Non-zero to abort
        except Exception as e:
            print(f"[Hook {self.name}] Error: {e}")
            return 1  # Non-zero to abort
