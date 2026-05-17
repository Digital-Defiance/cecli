"""Dispatch tool - allows the primary agent to spawn sub-agents."""

from cecli.tools.utils.base_tool import BaseTool


class Tool(BaseTool):
    NORM_NAME = "dispatch"
    TRACK_INVOCATIONS = True
    SCHEMA = {
        "type": "function",
        "function": {
            "name": "Dispatch",
            "description": (
                "Dispatch a specialized sub-agent to handle a sub-task autonomously. "
                "The sub-agent works independently and returns a summary when done."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the sub-agent to dispatch.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Task description to give the sub-agent.",
                    },
                },
                "required": ["name", "prompt"],
            },
        },
    }

    @classmethod
    async def execute(cls, coder, **kwargs):
        """Dispatch a sub-agent to work on a sub-task."""
        name = kwargs.get("name", "")
        prompt = kwargs.get("prompt", "")

        if not name:
            return "Error: 'name' parameter is required."
        if not prompt:
            return "Error: 'prompt' parameter is required."

        # Get the AgentService for this coder
        from cecli.helpers.agents.service import AgentService

        try:
            agent_service = AgentService.get_instance(coder)
            summary = await agent_service.invoke(name, prompt, blocking=True)
            if summary:
                return f"Sub-agent '{name}' completed:\n{summary}"
            return f"Sub-agent '{name}' completed (no summary)."
        except ValueError as e:
            return f"Error: {e}"
        except RuntimeError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error dispatching sub-agent '{name}': {e}"
