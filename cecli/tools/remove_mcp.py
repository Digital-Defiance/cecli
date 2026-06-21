from typing import List

from cecli.commands.utils.helpers import (
    is_server_globally_excluded,
    update_server_registration,
)
from cecli.tools.utils.base_tool import BaseTool


class Tool(BaseTool):
    NORM_NAME = "remove-mcp"
    SCHEMA = {
        "type": "function",
        "function": {
            "name": "RemoveMCP",
            "description": (
                "Remove (unload) MCP server(s) by name, or use '*' to remove all connected servers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "servers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "A list of MCP server names to remove. Use '*' to remove all."
                        ),
                    }
                },
                "required": ["servers"],
            },
        },
    }

    @classmethod
    async def execute(cls, coder, servers: List[str]):
        """Execute the remove-mcp tool with given parameters."""
        if not coder.mcp_manager or not coder.mcp_manager.servers:
            return "No MCP servers are configured."

        results = []
        servers_to_action = []

        # Determine which servers to act on
        if servers == ["*"]:
            servers_to_action.extend(s.name for s in coder.mcp_manager.connected_servers)
        else:
            for server_name in servers:
                server = coder.mcp_manager.get_server(server_name)
                if not server:
                    results.append(f"MCP server {server_name} does not exist.")
                elif server.name not in {s.name for s in coder.mcp_manager.connected_servers}:
                    results.append(f"Server {server_name} is not currently connected.")
                else:
                    servers_to_action.append(server.name)

        # If there are no servers to act on but we have preliminary results (like errors), return them
        if not servers_to_action and results:
            return "\n".join(results)

        # If there are no servers to remove at all
        if not servers_to_action:
            return "No servers to remove."

        # Process the removal with server registration awareness
        for server_name in servers_to_action:
            # Never remove the "local" server
            if server_name == "Local":
                results.append("Cannot remove 'Local' server")
                continue

            # Force-exclude on the primary (active) coder
            update_server_registration(coder, server_name, "exclude", force=True)

            # Check if all coders in the hierarchy have this server excluded
            all_excluded = is_server_globally_excluded(coder, server_name)

            if all_excluded:
                coder.interrupt_event.clear()
                did_disconnect, interrupted = await coder.coroutines.interruptible(
                    coder.mcp_manager.disconnect_server(server_name),
                    coder.interrupt_event,
                )

                if interrupted:
                    results.append(f"Interrupted: {server_name}")
                    continue
                if did_disconnect:
                    results.append(f"Removed server: {server_name}")
                else:
                    results.append(f"Unable to remove server: {server_name}")
            else:
                results.append(f"Removed from active coder, still active for others: {server_name}")

        return "\n".join(results)
