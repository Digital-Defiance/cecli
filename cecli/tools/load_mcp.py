from typing import List

from cecli.commands.utils.helpers import (
    iter_all_coders,
    update_server_registration,
)
from cecli.tools.utils.base_tool import BaseTool


class Tool(BaseTool):
    NORM_NAME = "load-mcp"
    SCHEMA = {
        "type": "function",
        "function": {
            "name": "LoadMCP",
            "description": "Load MCP server(s) by name, or use '*' to load all enabled servers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "servers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of MCP server names to load. Use '*' to load all.",
                    }
                },
                "required": ["servers"],
            },
        },
    }

    @classmethod
    async def execute(cls, coder, servers: List[str]):
        """Execute the load-mcp tool with given parameters."""
        if not coder.mcp_manager or not coder.mcp_manager.servers:
            return "No MCP servers found, nothing to load."

        results = []
        servers_to_load = []

        if servers == ["*"]:
            for server in coder.mcp_manager.servers:
                if server.name in {s.name for s in coder.mcp_manager.connected_servers}:
                    results.append(f"Server already loaded: {server.name}")
                    continue
                auto_connect = server.config.get("enabled", True)
                if not auto_connect:
                    results.append(f"Skipping server (not enabled by default): {server.name}")
                    continue
                servers_to_load.append(server)
        else:
            for server_name in servers:
                server = coder.mcp_manager.get_server(server_name)
                if server is None:
                    results.append(f"MCP server {server_name} does not exist.")
                else:
                    servers_to_load.append(server)

        if not servers_to_load and results:
            return "\n".join(results)

        # Before connecting any new server, convert coders with empty included sets
        # to explicit include lists of all currently connected MCP servers.
        # This moves them from "implicitly include all" to explicit state-machine
        # management, preventing the new server from being implicitly available
        # to all coders.
        connected_names = {s.name for s in coder.mcp_manager.connected_servers}
        if connected_names:
            for c in iter_all_coders(coder):
                if not c.registered_servers["included"]:
                    included = set(connected_names) - c.registered_servers["excluded"]
                    if c.edit_format in ("agent", "subagent"):
                        included.add("Local")  # "local" is always available
                    c.registered_servers["included"] = included

        # Process the loading
        for server in servers_to_load:
            server_name = server.name
            if server_name in {s.name for s in coder.mcp_manager.connected_servers}:
                results.append(f"Server already loaded: {server_name}")
                continue

            coder.interrupt_event.clear()
            did_connect, interrupted = await coder.coroutines.interruptible(
                coder.mcp_manager.connect_server(server_name),
                coder.interrupt_event,
            )

            if interrupted:
                results.append(f"Interrupted: {server_name}")
                continue
            if did_connect:
                # Force-include on the primary (active) coder
                update_server_registration(coder, server_name, "include", force=True)

                # Safe-exclude on all other coders (respects existing inclusions)
                for other_coder in iter_all_coders(coder):
                    if other_coder is coder:
                        continue
                    update_server_registration(other_coder, server_name, "exclude", force=False)

                results.append(f"Loaded server: {server_name}")
            else:
                results.append(f"Unable to load server: {server_name}")

        return "\n".join(results)
