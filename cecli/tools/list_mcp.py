from cecli.tools.utils.base_tool import BaseTool


class Tool(BaseTool):
    NORM_NAME = "list-mcp"
    SCHEMA = {
        "type": "function",
        "function": {
            "name": "ListMcp",
            "description": "List all loaded and available MCP servers.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }

    @classmethod
    def execute(cls, coder, **kwargs):
        """List all loaded and available MCP servers."""
        if not coder.mcp_manager:
            return "MCP manager is not available."

        all_servers = coder.mcp_manager.servers
        connected_servers = coder.mcp_manager.connected_servers

        loaded_server_names = {server.name for server in connected_servers}
        available_servers = [
            server for server in all_servers if server.name not in loaded_server_names
        ]

        result = []
        if loaded_server_names:
            result.append("Loaded MCP Servers:")
            for name in sorted(list(loaded_server_names)):
                result.append(f"- {name}")
        else:
            result.append("No MCP servers are currently loaded.")

        result.append("")

        if available_servers:
            result.append("Available MCP Servers:")
            for server in sorted(available_servers, key=lambda s: s.name):
                result.append(f"- {server.name}")
        else:
            result.append("No other MCP servers are available to load.")

        return "\n".join(result)
