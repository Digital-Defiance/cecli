import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cecli.tools import update_todo_list
from cecli.tools.update_todo_list import format_task_lines, normalize_task_items
from cecli.tools.utils.helpers import normalize_json_array


def test_normalize_json_array_parses_string():
    items = normalize_json_array('[{"task": "a", "done": false}]', param_name="tasks")
    assert len(items) == 1
    assert items[0]["task"] == "a"


def test_format_task_lines_accepts_json_string():
    tasks_json = json.dumps(
        [
            {"task": "Draft roadmap items in docs/ROADMAP.md", "done": False},
            {"task": "Ship fix", "done": True},
        ]
    )
    done, remaining = format_task_lines(tasks_json)
    assert len(remaining) == 1
    assert "Draft roadmap" in remaining[0]
    assert len(done) == 1
    assert "Ship fix" in done[0]
    assert all(len(line) > 5 for line in remaining + done)


def test_normalize_task_items_does_not_split_characters():
    tasks_json = json.dumps([{"task": "Only one task", "done": False}])
    items = normalize_task_items(tasks_json)
    assert len(items) == 1
    assert items[0]["task"] == "Only one task"


class DummyIO:
    def __init__(self):
        self.tool_output = Mock()
        self.tool_error = Mock()
        self.tool_warning = Mock()


class DummyCoder:
    def __init__(self):
        self.io = DummyIO()
        self.pretty = False
        self.verbose = False


def test_format_output_accepts_tasks_as_json_string():
    coder = DummyCoder()
    args = json.dumps(
        {
            "tasks": (
                '[{"task": "Draft roadmap items", "done": false}, '
                '{"task": "Write tests", "done": true}]'
            )
        }
    )
    tool_response = SimpleNamespace(
        function=SimpleNamespace(name="UpdateTodoList", arguments=args)
    )

    update_todo_list.Tool.format_output(
        coder,
        mcp_server=SimpleNamespace(name="test"),
        tool_response=tool_response,
    )

    output_text = "\n".join(call.args[0] for call in coder.io.tool_output.call_args_list)
    assert "Draft roadmap items" in output_text
    assert "Write tests" in output_text
    assert output_text.count("○ ") <= 2
    coder.io.tool_error.assert_not_called()
