"""Delegate tool - allows the primary agent to spawn sub-agents."""

import asyncio
import json

from cecli.tools.utils.base_tool import BaseTool
from cecli.tools.utils.output import color_markers, tool_footer, tool_header


class Tool(BaseTool):
    NORM_NAME = "delegate"
    TRACK_INVOCATIONS = True
    SCHEMA = {
        "type": "function",
        "function": {
            "name": "Delegate",
            "description": (
                "Delegate one or more specialized sub-agents to handle sub-tasks autonomously. "
                "Accepts an array of delegations to enable parallel task dispatch."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "delegations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Name of the sub-agent to delegate to.",
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": "Task description to give the sub-agent.",
                                },
                            },
                            "required": ["name", "prompt"],
                        },
                        "description": "Array of delegation tasks to execute in parallel.",
                    }
                },
                "required": ["delegations"],
            },
        },
    }

    @classmethod
    async def execute(cls, coder, **kwargs):
        """Delegate one or more sub-agents to work on sub-tasks in parallel."""
        delegations = kwargs.get("delegations", [])

        if not delegations or not isinstance(delegations, list):
            return "Error: 'delegations' parameter must be a non-empty array of {name, prompt} objects."

        # Validate each delegation item has the required fields
        for i, d in enumerate(delegations):
            if not isinstance(d, dict):
                return f"Error: delegations[{i}] is not an object."
            if "name" not in d or not d["name"]:
                return f"Error: delegations[{i}] is missing a 'name'."
            if "prompt" not in d or not d["prompt"]:
                return f"Error: delegations[{i}] is missing a 'prompt'."

        from cecli.helpers.agents.service import AgentService

        agent_service = AgentService.get_instance(coder)

        # Track results with status flag instead of fragile emoji checks
        results: list[tuple[bool, str]] = []

        async def _run_one(name: str, prompt: str) -> tuple[bool, str]:
            """Run a single sub-agent and return a (success, formatted_message) tuple."""
            try:
                summary = await agent_service.invoke(name, prompt, blocking=True)
                if summary:
                    return True, f"Sub-agent '{name}' completed:\n{summary}"
                return True, f"Sub-agent '{name}' completed (no summary)."
            except (ValueError, RuntimeError) as e:
                return False, f"Sub-agent '{name}' failed: {e}"
            except Exception as e:
                return False, f"Sub-agent '{name}' failed with unexpected error: {e}"

        # Dispatch all delegations in parallel
        tasks = [_run_one(d["name"], d["prompt"]) for d in delegations]
        raw_results = await asyncio.gather(*tasks)

        # Separate success flag from message
        for success, msg in raw_results:
            results.append((success, msg))

        # Build a consolidated report
        n_ok = sum(1 for ok, _ in results if ok)
        n_total = len(results)
        separator = "\n" + "─" * 60 + "\n"
        combined = separator.join(msg for _, msg in results)

        return f"📋 Delegation results ({n_ok}/{n_total} succeeded):" f"{separator}{combined}"

    @classmethod
    def format_output(cls, coder, mcp_server, tool_response):
        """Format output for Delegate tool - show each delegation's agent and task."""
        color_start, color_end = color_markers(coder)

        try:
            params = json.loads(tool_response.function.arguments)
        except json.JSONDecodeError:
            coder.io.tool_error("Invalid Tool JSON")
            return

        tool_header(coder=coder, mcp_server=mcp_server, tool_response=tool_response)

        delegations = params.get("delegations", [])
        if delegations:
            coder.io.tool_output("")
            for i, d in enumerate(delegations):
                name = d.get("name", "")
                prompt = d.get("prompt", "")
                coder.io.tool_output(f"{color_start}delegation_{i + 1}:{color_end}")
                coder.io.tool_output(f"agent: {name}")
                coder.io.tool_output(f"task: {prompt}")
                if i < len(delegations) - 1:
                    coder.io.tool_output("")

        tool_footer(coder=coder, tool_response=tool_response)
