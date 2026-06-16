from unittest.mock import AsyncMock, MagicMock

import pytest

from cecli.tools.remove_mcp_tool import RemoveMcpTool


@pytest.mark.asyncio
async def test_remove_mcp_tool_success():
    """Test successful removal of an MCP server."""
    # Setup
    coder = MagicMock()
    coder.mcp_manager = MagicMock()
    server = MagicMock()
    server.name = "test-server"
    server.config.get.return_value = True  # auto_connect enabled
    coder.mcp_manager.get_server.return_value = server
    coder.mcp_manager.connected_servers = {"test-server": server}
    # Mock disconnect_server as an AsyncMock that returns (True, False)
    coder.mcp_manager.disconnect_server = AsyncMock(return_value=(True, False))

    # Mock the interruptible method to execute the coroutine
    async def mock_interruptible(coro, event):
        return await coro, False

    coder.coroutines = MagicMock()
    coder.coroutines.interruptible = mock_interruptible
    coder.interrupt_event = MagicMock()

    # Execute
    result = await RemoveMcpTool.execute(coder, ["test-server"])

    # Assertions
    assert "Removed server: test-server" in result
    coder.mcp_manager.disconnect_server.assert_awaited_once_with("test-server")


@pytest.mark.asyncio
async def test_remove_mcp_tool_non_existent():
    """Test removing a non-existent MCP server."""
    # Setup
    coder = MagicMock()
    coder.mcp_manager = MagicMock()
    # Create a mock server that exists (to bypass the 'no servers' check)
    existing_server = MagicMock()
    existing_server.name = "existing-server"
    existing_server.config.get.return_value = True
    coder.mcp_manager.servers = [existing_server]
    # But the one we're looking for doesn't exist
    coder.mcp_manager.get_server.return_value = None

    # Execute
    result = await RemoveMcpTool.execute(coder, ["non-existent-server"])

    # Assertions
    assert "MCP server non-existent-server does not exist." in result

    assert "MCP server non-existent-server does not exist." in result


@pytest.mark.asyncio
async def test_remove_mcp_tool_not_connected():
    """Test removing a server that is not connected."""
    coder = MagicMock()
    coder.mcp_manager = MagicMock()
    server = MagicMock()
    server.name = "test-server"
    coder.mcp_manager.servers = [server]
    coder.mcp_manager.get_server.return_value = server
    coder.mcp_manager.connected_servers = {}

    result = await RemoveMcpTool.execute(coder, ["test-server"])

    assert "Server test-server is not currently connected." in result


@pytest.mark.asyncio
async def test_remove_mcp_tool_wildcard():
    """Test removing all servers with wildcard '*'."""
    coder = MagicMock()
    coder.mcp_manager = MagicMock()

    server1 = MagicMock()
    server1.name = "server1"
    server2 = MagicMock()
    server2.name = "server2"

    coder.mcp_manager.servers = [server1, server2]
    coder.mcp_manager.connected_servers = {"server1": server1, "server2": server2}
    coder.mcp_manager.disconnect_server = AsyncMock(return_value=True)

    async def mock_interruptible(coro, event):
        return await coro, False

    coder.coroutines = MagicMock()
    coder.coroutines.interruptible = mock_interruptible
    coder.interrupt_event = MagicMock()

    result = await RemoveMcpTool.execute(coder, ["*"])

    assert "Removed server: server1" in result
    assert "Removed server: server2" in result
    assert coder.mcp_manager.disconnect_server.await_count == 2
