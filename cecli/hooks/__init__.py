"""Hooks module for extending cecli functionality."""

from .base import BaseHook, CommandHook
from .integration import HookIntegration
from .manager import HookManager
from .registry import HookRegistry
from .types import METADATA_TEMPLATES, HookType

__all__ = [
    "BaseHook",
    "CommandHook",
    "HookIntegration",
    "HookManager",
    "HookRegistry",
    "HookType",
    "METADATA_TEMPLATES",
]
