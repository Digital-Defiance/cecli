"""SubAgentCoder - a Coder variant for sub-agents.

Extends AgentCoder but excludes the Dispatch tool from its tool schemas
so sub-agents cannot spawn further sub-agents.
"""

import logging
from typing import Dict, List

from cecli.coders.agent_coder import AgentCoder
from cecli.helpers.conversation.service import ConversationService
from cecli.tools.utils.registry import ToolRegistry

logger = logging.getLogger(__name__)


class SubAgentCoder(AgentCoder):
    """Coder for sub-agents that disallows spawning further sub-agents."""

    edit_format = "subagent"
    prompt_format = "subagent"

    def format_chat_chunks(self):
        """Override format_chat_chunks to inject sub-agent prompt as system message.

        Sub-agents inject their configured system prompt into the conversation
        instead of using the default main system prompt.
        Always restricts tools to exclude the 'dispatch' tool.
        """
        if not self.use_enhanced_context:
            chunks = super().format_chat_chunks()
            # Override tool schemas to exclude dispatch even in fallback path
            self.tool_schemas = self.get_local_tool_schemas()
            return chunks

        self.choose_fence()

        ConversationService.get_chunks(self).initialize_conversation_system()
        ConversationService.get_chunks(self).cleanup_files()
        ConversationService.get_chunks(self).add_file_list_reminder()
        ConversationService.get_chunks(self).add_rules_messages()
        ConversationService.get_chunks(self).add_repo_map_messages()
        ConversationService.get_chunks(self).add_readonly_files_messages()
        ConversationService.get_chunks(self).add_chat_files_messages()
        ConversationService.get_chunks(self).add_randomized_cta()

        return ConversationService.get_manager(self).get_messages_dict()

    def get_local_tool_schemas(self) -> List[Dict]:
        """Return tool schemas, excluding the 'dispatch' tool."""
        registry = ToolRegistry.build_registry(agent_config=self.agent_config)
        schemas = []
        for name, tool_class in registry.items():
            if name == "dispatch":
                continue
            if tool_class.SCHEMA:
                schemas.append(tool_class.SCHEMA)
        return schemas
