import json
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseHook
from .types import HookType


class HookManager:
    """Central registry and dispatcher for hooks."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super(HookManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the hook manager."""
        if self._initialized:
            return

        self._hooks_by_type: Dict[str, List[BaseHook]] = defaultdict(list)
        self._hooks_by_name: Dict[str, BaseHook] = {}
        self._state_file = Path.home() / ".cecli" / "hooks_state.json"
        self._state_lock = threading.Lock()

        # Ensure state directory exists
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

        self._initialized = True

    def register_hook(self, hook: BaseHook) -> None:
        """Register a hook instance.

        Args:
            hook: The hook instance to register.

        Raises:
            ValueError: If hook with same name already exists.
        """
        with self._lock:
            if hook.name in self._hooks_by_name:
                raise ValueError(f"Hook with name '{hook.name}' already exists")

            # Load saved state if available
            # self._load_hook_state(hook)

            # Add to registries
            self._hooks_by_type[hook.type.value].append(hook)
            self._hooks_by_name[hook.name] = hook

            # Sort hooks by priority (lower = higher priority)
            self._hooks_by_type[hook.type.value].sort(key=lambda h: h.priority)

    def get_hooks(self, hook_type: str) -> List[BaseHook]:
        """Return hooks of specific type, sorted by priority.

        Args:
            hook_type: The hook type to retrieve.

        Returns:
            List of hooks of the specified type, sorted by priority.
        """
        with self._lock:
            hooks = self._hooks_by_type.get(hook_type, [])
            # Return only enabled hooks
            return [h for h in hooks if h.enabled]

    def get_all_hooks(self) -> Dict[str, List[BaseHook]]:
        """Get all hooks grouped by type for display.

        Returns:
            Dictionary mapping hook types to lists of hooks.
        """
        with self._lock:
            return {hook_type: hooks.copy() for hook_type, hooks in self._hooks_by_type.items()}

    def hook_exists(self, name: str) -> bool:
        """Check if a hook exists by name.

        Args:
            name: The hook name to check.

        Returns:
            True if hook exists, False otherwise.
        """
        with self._lock:
            return name in self._hooks_by_name

    def enable_hook(self, name: str) -> bool:
        """Enable a hook by name and persist state.

        Args:
            name: The hook name to enable.

        Returns:
            True if hook was enabled, False if hook not found.
        """
        with self._lock:
            if name not in self._hooks_by_name:
                return False

            hook = self._hooks_by_name[name]
            hook.enabled = True
            # self._save_state()
            return True

    def disable_hook(self, name: str) -> bool:
        """Disable a hook by name and persist state.

        Args:
            name: The hook name to disable.

        Returns:
            True if hook was disabled, False if hook not found.
        """
        with self._lock:
            if name not in self._hooks_by_name:
                return False

            hook = self._hooks_by_name[name]
            hook.enabled = False
            # self._save_state()
            return True

    async def call_hooks(self, hook_type: str, coder: Any, metadata: Dict[str, Any]) -> bool:
        """Execute all hooks of a type.

        Args:
            hook_type: The hook type to execute.
            coder: The coder instance providing context.
            metadata: Dictionary with metadata about the current operation.

        Returns:
            True if all hooks succeeded (or no hooks to run), False if any hook failed.
        """
        hooks = self.get_hooks(hook_type)
        if not hooks:
            return True

        all_succeeded = True

        for hook in hooks:
            if not hook.enabled:
                continue

            try:
                result = await hook.execute(coder, metadata)

                # Check if hook indicates failure
                if hook_type in [HookType.PRE_TOOL.value, HookType.POST_TOOL.value]:
                    # For tool hooks, falsy value or non-zero exit code indicates failure
                    if isinstance(result, bool):
                        # Boolean result: False indicates failure
                        if not result:
                            print(f"[Hook {hook.name}] Returned False")
                            all_succeeded = False
                    elif isinstance(result, int):
                        # Integer result: non-zero indicates failure
                        if result != 0:
                            print(f"[Hook {hook.name}] Failed with exit code {result}")
                            all_succeeded = False
                    elif not result:
                        # Other falsy value indicates failure
                        print(f"[Hook {hook.name}] Returned falsy value: {result}")
                        all_succeeded = False

            except Exception as e:
                print(f"[Hook {hook.name}] Error during execution: {e}")
                # Continue with other hooks even if one fails

        return all_succeeded

    def _load_hook_state(self, hook: BaseHook) -> None:
        """Load saved state for a hook."""
        if not self._state_file.exists():
            return

        try:
            with self._state_lock:
                with open(self._state_file, "r") as f:
                    state = json.load(f)

                if hook.name in state:
                    hook.enabled = state[hook.name]
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load hook state from {self._state_file}: {e}")

    def _save_state(self) -> None:
        """Save hook states to configuration file."""
        try:
            with self._state_lock:
                # Create backup of existing state
                if self._state_file.exists():
                    backup_file = self._state_file.with_suffix(".json.bak")
                    import shutil

                    shutil.copy2(self._state_file, backup_file)

                # Save current state
                state = {name: hook.enabled for name, hook in self._hooks_by_name.items()}

                # Write to temporary file first, then rename (atomic write)
                temp_file = self._state_file.with_suffix(".json.tmp")
                with open(temp_file, "w") as f:
                    json.dump(state, f, indent=2)

                # Atomic rename
                temp_file.rename(self._state_file)

        except Exception as e:
            print(f"Warning: Could not save hook state to {self._state_file}: {e}")

    def _load_state(self) -> None:
        """Load hook states from configuration file."""
        if not self._state_file.exists():
            return

        try:
            with self._state_lock:
                with open(self._state_file, "r") as f:
                    state = json.load(f)

                # Apply loaded state to registered hooks
                for name, enabled in state.items():
                    if name in self._hooks_by_name:
                        self._hooks_by_name[name].enabled = enabled

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load hook state from {self._state_file}: {e}")

    def clear(self) -> None:
        """Clear all registered hooks (for testing)."""
        with self._lock:
            self._hooks_by_type.clear()
            self._hooks_by_name.clear()
