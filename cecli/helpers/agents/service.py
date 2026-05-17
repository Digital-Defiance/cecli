"""Agent service for managing sub-agents.

Provides the singleton AgentService (keyed by parent coder UUID)
that tracks sub-agent info and handles invoke/spawn/wait lifecycle.
"""

import asyncio
import logging
import weakref
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import cecli.models as models

logger = logging.getLogger(__name__)


class SubAgentStatus(Enum):
    """Status of a sub-agent."""

    CREATED = "created"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class SubAgentInfo:
    """Information about a running sub-agent."""

    name: str
    coder: Any  # SubAgentCoder instance
    parent_uuid: str
    status: SubAgentStatus = SubAgentStatus.CREATED
    summary: Optional[str] = None
    error: Optional[str] = None
    generate_task: Optional[asyncio.Task] = (
        None  # Track the generate() task for cancellation/monitoring
    )


class AgentService:
    """Singleton service for managing sub-agents per parent coder.

    Pattern matches ObservationService — instances are keyed by parent
    coder.uuid so each primary agent session gets its own service.
    """

    _instances: Dict[str, "AgentService"] = {}
    _global_registry: Dict[str, Any] = {}  # name -> SubAgentConfig (from .md files)
    # UUID -> weakref of coder instance for convenient lookup
    _uuid_coder_map: Dict[str, weakref.ref] = {}

    # ------------------------------------------------------------------ #
    # Singleton
    # ------------------------------------------------------------------ #

    @classmethod
    def get_instance(cls, coder) -> "AgentService":
        """Return the AgentService for *coder* (keyed by coder.uuid).

        If the coder has a parent_uuid, returns the parent's service
        instead so sub-agent switching can find sibling sub-agents.
        """
        # If this coder is a sub-agent, use the parent's service
        parent_uuid = coder.parent_uuid
        if parent_uuid and parent_uuid in cls._instances:
            parent_service = cls._instances[parent_uuid]
            # Update sub-agent coder reference on the parent instance.
            # Coders inherit uuids through state operation chains, so the
            # same uuid can refer to different coder instances over time.
            existing_info = parent_service.sub_agents.get(coder.uuid)
            if existing_info and existing_info.coder != coder:
                existing_info.coder = coder
                cls._uuid_coder_map[coder.uuid] = weakref.ref(coder)

            return parent_service

        uid = coder.uuid
        if uid not in cls._instances:
            cls._instances[uid] = cls(coder)

        # Update coder reference on AgentService Instance
        # as coders inherit uuids
        if cls._instances[uid].coder != coder:
            cls._instances[uid].coder = coder
            cls._uuid_coder_map[coder.uuid] = weakref.ref(coder)

        return cls._instances[uid]

    @classmethod
    def destroy_instance(cls, coder_uuid: str) -> None:
        """Explicitly remove a service instance (cleanup)."""
        cls._instances.pop(coder_uuid, None)

    # ------------------------------------------------------------------ #
    # Registry helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def get_registry(cls) -> Dict[str, Any]:
        """Return the global sub-agent registry (name -> config)."""
        return cls._global_registry

    @classmethod
    def register_subagent(cls, name: str, config: Any) -> None:
        """Register a sub-agent config by name."""
        cls._global_registry[name] = config

    @classmethod
    def unregister_subagent(cls, name: str) -> None:
        """Remove a sub-agent from the global registry."""
        cls._global_registry.pop(name, None)

    @classmethod
    def mark_sub_agent_finished(
        cls,
        sub_coder_uuid: str,
        parent_uuid: str,
        summary: Optional[str] = None,
    ) -> None:
        """Public API to mark a sub-agent as finished.

        Looks up the parent's AgentService by parent_uuid and updates
        the matching sub-agent's status and summary.

        Args:
            sub_coder_uuid: UUID of the sub-agent coder.
            parent_uuid: UUID of the parent coder.
            summary: Optional summary string from the sub-agent.
        """
        for uid, service in cls._instances.items():
            if uid != parent_uuid:
                continue
            for info in list(service.sub_agents.values()):
                if info.coder.uuid == sub_coder_uuid:
                    info.summary = summary or "(no summary)"
                    info.status = SubAgentStatus.FINISHED
                    return

    @classmethod
    def build_registry(cls, paths: List[str]) -> None:
        """Scan directories for .md sub-agent definition files and load them.

        Each .md file should contain YAML front matter with:
          ---
          name: <agent-name>
          model: <optional-model-override>
          ---
          <system prompt body>
        """
        from pathlib import Path

        from .config import parse_subagent_file

        for directory in paths:
            dir_path = Path(directory)
            if not dir_path.is_dir():
                continue
            for md_file in sorted(dir_path.glob("*.md")):
                try:
                    config = parse_subagent_file(str(md_file))
                    if config and config.name:
                        cls._global_registry[config.name] = config
                        logger.info("Loaded sub-agent '%s' from %s", config.name, md_file)
                except (ValueError, OSError) as exc:
                    logger.warning("Failed to parse sub-agent file %s: %s", md_file, exc)
                except Exception as exc:
                    logger.warning("Unexpected error parsing sub-agent file %s: %s", md_file, exc)

    # ------------------------------------------------------------------ #
    # Instance
    # ------------------------------------------------------------------ #

    def __init__(self, coder) -> None:
        self.coder = coder
        # Register the primary coder in the global uuid map
        if hasattr(coder, "uuid"):
            self._uuid_coder_map[str(coder.uuid)] = weakref.ref(coder)
        # uuid -> SubAgentInfo
        self.sub_agents: Dict[str, SubAgentInfo] = {}
        # Ordered list of sub-agent UUIDs for LRU reap
        self._sub_agent_order: List[str] = []

    @property
    def max_sub_agents(self) -> int:
        """Return the max number of sub-agents allowed for this coder."""
        return getattr(self.coder, "max_sub_agents", 3)

    # ------------------------------------------------------------------ #
    # Internal helpers
    @staticmethod
    def _get_tui(coder: Any) -> Any:
        """Dereference the TUI weakref from a coder, returning None if unavailable.

        The TUI stores itself on coders via ``coder.tui = weakref.ref(app)``,
        so it must be called (``tui()``) to obtain the live object.

        Args:
            coder: A coder instance that may have a ``tui`` attribute.

        Returns:
            The TUI application instance, or ``None`` if the weakref is dead
            or the coder has no ``tui`` attribute.
        """
        tui_ref = getattr(coder, "tui", None)
        if tui_ref is None:
            return None
        # weakref.ref objects are callable — calling them returns the live
        # reference or None if the object has been garbage-collected.
        if isinstance(tui_ref, weakref.ref):
            return tui_ref()
        # If it is already a plain reference (e.g., in tests), use it directly.
        return tui_ref

    # ------------------------------------------------------------------ #

    def _reap_finished_agent(self) -> None:
        """Remove the oldest FINISHED sub-agent (lazy reap)."""
        for coder_uuid in list(self._sub_agent_order):
            info = self.sub_agents.get(coder_uuid)
            if info and info.status == SubAgentStatus.FINISHED:
                self._cleanup_sub_agent(coder_uuid)
                return

    def _cleanup_sub_agent(self, agent_uuid: str) -> None:
        """Remove agent instance from tracking and notify TUI if possible."""
        info = self.sub_agents.pop(agent_uuid, None)
        if agent_uuid in self._sub_agent_order:
            self._sub_agent_order.remove(agent_uuid)

        if info is None:
            return

        # Destroy conversation resources for the sub-agent
        from cecli.helpers.conversation.service import ConversationService

        try:
            ConversationService.destroy_instances(info.coder.uuid)
        except (KeyError, AttributeError, RuntimeError):
            logger.warning("Failed to destroy conversation instances", exc_info=True)

        # Notify TUI to remove the sub-agent container
        try:
            # Use self.coder (parent) for TUI lookup — sub-agents don't have
            # their own tui attribute; only the primary coder stores it.
            tui = self._get_tui(self.coder)
            if tui is not None:
                tui.call_from_thread(tui.remove_sub_agent_container, info.coder.uuid)
        except (AttributeError, RuntimeError):
            logger.warning("Failed to notify TUI to remove sub-agent container", exc_info=True)

        # Cancel any tracked generate task to avoid floating tasks
        if info.generate_task is not None and not info.generate_task.done():
            info.generate_task.cancel()

        # Reset foreground tracking if the cleaned agent was foreground
        if getattr(self, "_foreground_uuid", None) == info.coder.uuid:
            self._foreground_uuid = None

        # Remove from global coder lookup and clean up our service tracking
        # Note: this destroys the service instance keyed by the sub-agent's uuid,
        # not the parent's service instance. The parent's instance is cleaned
        # up separately in cleanup_all_for_parent().
        self._uuid_coder_map.pop(info.coder.uuid, None)
        self.destroy_instance(info.coder.uuid)

    def _check_max_sub_agents(self) -> None:
        """If we've hit max_sub_agents, reap the oldest finished one.

        Raises RuntimeError if no finished agents can be reaped.
        """
        active_count = sum(
            1 for info in self.sub_agents.values() if info.status != SubAgentStatus.FINISHED
        )
        if active_count < self.max_sub_agents:
            return

        # Try to reap a finished agent via the shared helper
        self._reap_finished_agent()

        # Recalculate active count after reaping
        active_count = sum(
            1 for info in self.sub_agents.values() if info.status != SubAgentStatus.FINISHED
        )
        if active_count >= self.max_sub_agents:
            raise RuntimeError(
                f"Maximum sub-agents ({self.max_sub_agents}) reached. "
                "Wait for one to finish or use /reap-agent to free resources."
            )

    async def _create_sub_agent_coder(self, name: str) -> Tuple[Any, SubAgentInfo]:
        """Create a sub-agent coder, register it, and set up its container and prompt.

        Shared helper used by both ``invoke()`` and ``spawn()`` to eliminate
        code duplication in the sub-agent creation pipeline.

        Args:
            name: Name of the sub-agent to create.

        Returns:
            Tuple of ``(new_coder, info)``.

        Raises:
            ValueError: If the named sub-agent is not registered.
            RuntimeError: If the maximum number of sub-agents is reached.
        """
        config = self._global_registry.get(name)
        if not config:
            raise ValueError(
                f"Unknown sub-agent '{name}'. " f"Available: {list(self._global_registry.keys())}"
            )

        self._check_max_sub_agents()

        from cecli.coders import Coder

        parent_coder = self.coder
        new_uuid = str(uuid4())

        kwargs = dict(
            io=parent_coder.io,
            from_coder=parent_coder,
            edit_format="subagent",
            cur_messages=[],
            uuid=new_uuid,
            parent_uuid=parent_coder.uuid,
        )

        model_override = getattr(config, "model", None)
        if model_override:
            kwargs["main_model"] = models.Model(model_override, from_model=parent_coder.main_model)

        new_coder = await Coder.create(**kwargs)
        # IOProxy wrapping is handled by base_coder.py's Coder.__init__

        # Register in global coder lookup
        self._uuid_coder_map[new_uuid] = weakref.ref(new_coder)

        info = SubAgentInfo(
            name=name,
            coder=new_coder,
            parent_uuid=parent_coder.uuid,
            status=SubAgentStatus.CREATED,
        )

        self.sub_agents[new_coder.uuid] = info
        self._sub_agent_order.append(new_coder.uuid)

        # Notify TUI to create a container
        try:
            tui = self._get_tui(parent_coder)
            if tui is not None:
                tui.call_from_thread(tui.create_sub_agent_container, new_uuid, name)
        except Exception:
            logger.warning("Failed to notify TUI to create sub-agent container", exc_info=True)

        # Initialize system prompt from config
        system_prompt = getattr(config, "prompt", "")
        from cecli.helpers.conversation.service import ConversationService

        ConversationService.get_chunks(new_coder).add_system_message(system_prompt)

        return new_coder, info

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start_generate_task(self, info: SubAgentInfo, user_message: str) -> asyncio.Task:
        """Start a sub-agent's generate task in the background with status management.

        Sets status to RUNNING before starting, and handles FINISHED/ERROR
        when the task completes or fails. Stores the task on ``info.generate_task``
        for cancellation/monitoring.

        Args:
            info: The SubAgentInfo for the sub-agent.
            user_message: The user message to pass to ``generate()``.

        Returns:
            The ``asyncio.Task`` wrapping ``generate()``.
        """

        async def _run_generate():
            info.status = SubAgentStatus.RUNNING
            try:
                await info.coder.generate(user_message=user_message, preproc=True)
                if info.status == SubAgentStatus.RUNNING:
                    info.status = SubAgentStatus.FINISHED
                    info.summary = info.summary or "(completed without explicit summary)"
            except asyncio.CancelledError:
                info.status = SubAgentStatus.FINISHED
                info.summary = info.summary or "(interrupted)"
                logger.debug("Sub-agent %s generate cancelled (interrupted)", info.name)
                raise
            except Exception as exc:
                info.status = SubAgentStatus.ERROR
                info.error = str(exc)
                logger.error(
                    "Sub-agent %s generate failed: %s",
                    info.name,
                    exc,
                    exc_info=True,
                )
                raise

        # Cancel any previous generate task to prevent duplicate concurrent generates
        if info.generate_task is not None and not info.generate_task.done():
            info.generate_task.cancel()

        task = asyncio.create_task(_run_generate())
        info.generate_task = task
        return task

    async def invoke(self, name: str, prompt: str, blocking: bool = True) -> Optional[str]:
        """Invoke a sub-agent by name with the given prompt (blocking by default)."""
        new_coder, info = await self._create_sub_agent_coder(name)

        if not blocking:
            return None

        # Blocking: run the sub-agent with the prompt
        info.status = SubAgentStatus.RUNNING
        try:
            await new_coder.generate(user_message=prompt, preproc=True)
            if info.status == SubAgentStatus.RUNNING:
                info.status = SubAgentStatus.FINISHED
                info.summary = info.summary or "(completed without explicit summary)"
            summary = info.summary
            return summary
        except asyncio.CancelledError:
            info.status = SubAgentStatus.FINISHED
            info.summary = info.summary or "(interrupted)"
            raise
        except Exception as exc:
            info.status = SubAgentStatus.ERROR
            info.error = str(exc)
            raise

    async def spawn(self, name: str) -> None:
        """Spawn a sub-agent (non-blocking) that waits for user input."""
        await self._create_sub_agent_coder(name)

    async def wait(self, name: str) -> Optional[str]:
        """Wait for a sub-agent to finish and return its summary."""
        # Find by name (allows multiple instances of the same agent type)
        info = None
        for candidate in self.sub_agents.values():
            if candidate.name == name:
                info = candidate
                break
        if not info:
            raise ValueError(f"No sub-agent named '{name}' running.")

        if info.status == SubAgentStatus.FINISHED:
            return info.summary

        # Poll until finished
        while info.status not in (SubAgentStatus.FINISHED, SubAgentStatus.ERROR):
            await asyncio.sleep(0.5)

        if info.status == SubAgentStatus.ERROR:
            raise RuntimeError(f"Sub-agent '{name}' failed: {info.error}")

        return info.summary

    def get_active_agents(self) -> List[Dict[str, Any]]:
        """Return list of active sub-agents for display."""
        return [
            {
                "name": info.name,
                "uuid": info.coder.uuid,
                "status": info.status.value,
                "summary": info.summary,
            }
            for info in self.sub_agents.values()
        ]

    # ------------------------------------------------------------------ #
    # Foreground agent tracking
    # ------------------------------------------------------------------ #

    @property
    def foreground_uuid(self):
        """Get the UUID of the currently active (foreground) agent."""
        return getattr(self, "_foreground_uuid", None)

    @foreground_uuid.setter
    def foreground_uuid(self, uuid):
        """Set the UUID of the currently active (foreground) agent.

        Args:
            uuid: The UUID of the agent to make foreground, or None for primary.
        """
        self._foreground_uuid = uuid

    @property
    def foreground_coder(self):
        """Get the coder of the currently active (foreground) agent."""
        uuid = self.foreground_uuid
        if uuid is None or uuid == self.coder.uuid:
            return self.coder
        for info in self.sub_agents.values():
            if info.coder.uuid == uuid:
                return info.coder
        return self.coder

    def cleanup_all_for_parent(self) -> None:
        """Clean up all sub-agents when the parent session ends."""
        for uuid in list(self.sub_agents.keys()):
            self._cleanup_sub_agent(uuid)
        self._instances.pop(self.coder.uuid, None)
