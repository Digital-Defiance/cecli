"""Glued local-model tool JSON argument parsing."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cecli.coders.base_coder import Coder
from cecli.tools.grep import Tool as GrepTool
from cecli.tools.utils.helpers import merge_glued_json_objects, parse_tool_arguments


def test_parse_tool_arguments_merges_glued_objects_with_empty_fragments():
    raw = '{"limit": 15}{}{"path": "."}'
    assert parse_tool_arguments(raw) == {"limit": 15, "path": "."}


def test_parse_tool_arguments_merges_grep_style_glued_args():
    raw = (
        '{"limit": 15}{}{"searches": [{"file_pattern": "*.md", '
        '"pattern": "TODO|FIXME", "use_regex": true}]}'
    )
    out = parse_tool_arguments(raw)
    assert out["limit"] == 15
    assert out["searches"][0]["pattern"] == "TODO|FIXME"


def test_merge_glued_returns_none_for_non_object_chunks():
    assert merge_glued_json_objects(['["a"]', '{"b": 1}']) is None


def test_expand_concatenated_json_merges_instead_of_splitting(monkeypatch):
    """Dogfood: DeepSeek ``{…}{}{…}`` must not become three tool calls."""

    class MiniCoder(Coder):
        def __init__(self):
            pass

    coder = MiniCoder.__new__(MiniCoder)
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="ls",
            arguments='{"limit": 15}{}{"path": "."}',
        ),
    )
    expanded = coder._expand_concatenated_json([tool_call])
    assert len(expanded) == 1
    assert json.loads(expanded[0].function.arguments) == {"limit": 15, "path": "."}
    assert expanded[0].id == "call-1"


def test_grep_format_output_empty_searches_does_not_crash_tool_footer():
    coder = SimpleNamespace(
        io=SimpleNamespace(tool_error=Mock(), tool_output=Mock(), tool_warning=Mock()),
        verbose=False,
        pretty=False,
        tui=lambda: None,
    )
    tool_response = SimpleNamespace(
        function=SimpleNamespace(
            name="Grep",
            arguments='{"limit": 15}{}{"searches": []}',
        ),
    )
    GrepTool.format_output(
        coder,
        mcp_server=SimpleNamespace(name="Local"),
        tool_response=tool_response,
    )
    assert coder.io.tool_error.called
