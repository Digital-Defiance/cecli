"""
Tests for cecli/tools/dispatch.py — Dispatch tool execution.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDispatchTool:
    """Tests for the Dispatch tool (cecli.tools.dispatch)."""

    @pytest.mark.asyncio
    async def test_empty_name_returns_error(self):
        """Missing name returns error string."""
        from cecli.tools.dispatch import Tool

        result = await Tool.execute(None, name="", prompt="do it")
        assert "Error" in result
        assert "name" in result

    @pytest.mark.asyncio
    async def test_empty_prompt_returns_error(self):
        """Missing prompt returns error string."""
        from cecli.tools.dispatch import Tool

        result = await Tool.execute(None, name="reviewer", prompt="")
        assert "Error" in result
        assert "prompt" in result

    @pytest.mark.asyncio
    async def test_both_empty_returns_name_error(self):
        """Both empty — name error comes first."""
        from cecli.tools.dispatch import Tool

        result = await Tool.execute(None, name="", prompt="")
        assert "Error" in result
        assert "name" in result

    @pytest.mark.asyncio
    async def test_valid_dispatch_calls_invoke(self):
        """Valid params call AgentService.invoke with correct args."""
        from cecli.tools.dispatch import Tool

        mock_coder = MagicMock()
        mock_coder.uuid = "parent-uuid"

        with patch("cecli.helpers.agents.service.AgentService") as MockService:
            mock_instance = MagicMock()
            mock_instance.invoke = AsyncMock(return_value="review summary")
            MockService.get_instance.return_value = mock_instance

            result = await Tool.execute(mock_coder, name="reviewer", prompt="review this")

            MockService.get_instance.assert_called_once_with(mock_coder)
            mock_instance.invoke.assert_called_once_with("reviewer", "review this", blocking=True)
            assert "review summary" in result

    @pytest.mark.asyncio
    async def test_dispatch_no_summary(self):
        """When invoke returns None, returns appropriate message."""
        from cecli.tools.dispatch import Tool

        mock_coder = MagicMock()
        with patch("cecli.helpers.agents.service.AgentService") as MockService:
            mock_instance = MagicMock()
            mock_instance.invoke = AsyncMock(return_value=None)
            MockService.get_instance.return_value = mock_instance

            result = await Tool.execute(mock_coder, name="tester", prompt="test")
            assert "completed (no summary)" in result

    @pytest.mark.asyncio
    async def test_dispatch_value_error_returns_error_string(self):
        """ValueError from service returns error string."""
        from cecli.tools.dispatch import Tool

        mock_coder = MagicMock()
        with patch("cecli.helpers.agents.service.AgentService") as MockService:
            mock_instance = MagicMock()
            mock_instance.invoke = AsyncMock(side_effect=ValueError("unknown agent"))
            MockService.get_instance.return_value = mock_instance

            result = await Tool.execute(mock_coder, name="ghost", prompt="x")
            assert "Error" in result
            assert "unknown agent" in result

    @pytest.mark.asyncio
    async def test_dispatch_runtime_error_returns_error_string(self):
        """RuntimeError from service returns error string."""
        from cecli.tools.dispatch import Tool

        mock_coder = MagicMock()
        with patch("cecli.helpers.agents.service.AgentService") as MockService:
            mock_instance = MagicMock()
            mock_instance.invoke = AsyncMock(side_effect=RuntimeError("max reached"))
            MockService.get_instance.return_value = mock_instance

            result = await Tool.execute(mock_coder, name="reviewer", prompt="x")
            assert "Error" in result
            assert "max reached" in result

    @pytest.mark.asyncio
    async def test_unexpected_exception_caught(self):
        """Any other exception returns error string (doesn't propagate)."""
        from cecli.tools.dispatch import Tool

        mock_coder = MagicMock()
        with patch("cecli.helpers.agents.service.AgentService") as MockService:
            mock_instance = MagicMock()
            mock_instance.invoke = AsyncMock(side_effect=Exception("unexpected"))
            MockService.get_instance.return_value = mock_instance

            result = await Tool.execute(mock_coder, name="reviewer", prompt="x")
            assert "Error" in result
            assert "unexpected" in result
