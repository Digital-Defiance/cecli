import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cecli.tools import read_range
from cecli.tools.read_range import normalize_show_ops


class DummyIO:
    def __init__(self):
        self.tool_error = Mock()
        self.tool_warning = Mock()
        self.tool_output = Mock()

    def read_text(self, path):
        return Path(path).read_text()

    def write_text(self, path, content):
        Path(path).write_text(content)


class DummyCoder:
    def __init__(self, root):
        self.root = str(root)
        self.repo = SimpleNamespace(root=str(root))
        self.io = DummyIO()
        self.pretty = False
        self.verbose = False
        import uuid

        self.uuid = str(uuid.uuid4())  # Generate unique UUID for each instance

        self.turn_count = 0

    def abs_root_path(self, file_path):
        path = Path(file_path)
        if path.is_absolute():
            return str(path)
        return str((Path(self.root) / path).resolve())

    def get_rel_fname(self, abs_path):
        return str(Path(abs_path).resolve().relative_to(self.root))


@pytest.fixture
def coder_with_file(tmp_path):
    file_path = tmp_path / "example.txt"
    file_path.write_text("alpha\nbeta\ngamma\n")
    coder = DummyCoder(tmp_path)
    return coder, file_path


def test_pattern_with_zero_line_number_is_allowed(coder_with_file):
    coder, file_path = coder_with_file

    result = read_range.Tool.execute(
        coder,
        show=[
            {
                "file_path": "example.txt",
                "start_text": "beta",
                "end_text": "beta",
                "padding": 0,
            }
        ],
    )

    # show_numbered_context now returns a new formatted context message
    assert "Retrieved context for 1 operation(s)" in result
    coder.io.tool_error.assert_not_called()


def test_empty_pattern_uses_line_number(coder_with_file):
    coder, file_path = coder_with_file

    result = read_range.Tool.execute(
        coder,
        show=[
            {
                "file_path": "example.txt",
                "start_text": "beta",
                "end_text": "beta",
                "padding": 0,
            }
        ],
    )

    # show_numbered_context now returns a static success message
    assert "Retrieved context for 1 operation(s)" in result
    coder.io.tool_error.assert_not_called()


def test_conflicting_pattern_and_line_number_raise(coder_with_file):
    coder, file_path = coder_with_file

    # Test that missing start_text raises an error
    result = read_range.Tool.execute(
        coder,
        show=[
            {
                "file_path": "example.txt",
                "end_text": "beta",
                "padding": 0,
            }
        ],
    )

    assert "Provide both 'start_text' and 'end_text'" in result
    coder.io.tool_error.assert_called()


def test_target_symbol_empty_string_treated_as_missing():
    from cecli.tools.utils import helpers
    from cecli.tools.utils.helpers import ToolError

    with pytest.raises(ToolError, match="Must specify either target_symbol or start_pattern"):
        helpers.determine_line_range(
            coder=SimpleNamespace(repo_map=None),  # repo_map not used in this path
            file_path="dummy",
            lines=["a", "b"],
            target_symbol="",
            start_pattern_line_index=None,
            end_pattern=None,
            line_count=1,
        )


def test_multiline_pattern_search(coder_with_file):
    coder, file_path = coder_with_file
    # file_path contains "alpha\nbeta\ngamma\n"

    result = read_range.Tool.execute(
        coder,
        show=[
            {
                "file_path": "example.txt",
                "start_text": "alpha\nbeta",
                "end_text": "beta\ngamma",
                "padding": 0,
            }
        ],
    )

    assert "Retrieved context for 1 operation(s)" in result
    coder.io.tool_error.assert_not_called()


def test_normalize_show_ops_accepts_json_string():
    ops = normalize_show_ops(
        '[{"file_path": "docs/ROADMAP.md", "start_text": "@000", "end_text": "\\n"}]'
    )
    assert len(ops) == 1
    assert ops[0]["file_path"] == "docs/ROADMAP.md"
    assert ops[0]["start_text"] == "@000"


def test_execute_accepts_show_as_json_string(coder_with_file):
    coder, _file_path = coder_with_file
    show_json = json.dumps([{"file_path": "example.txt", "start_text": "beta", "end_text": "beta"}])

    result = read_range.Tool.execute(coder, show=show_json)

    assert "Retrieved context for 1 operation(s)" in result
    coder.io.tool_error.assert_not_called()


def test_format_output_accepts_show_as_json_string(coder_with_file):
    coder, _file_path = coder_with_file
    args = json.dumps(
        {"show": '[{"file_path": "example.txt", "start_text": "alpha", "end_text": "gamma"}]'}
    )
    tool_response = SimpleNamespace(function=SimpleNamespace(name="ReadRange", arguments=args))

    read_range.Tool.format_output(
        coder,
        mcp_server=SimpleNamespace(name="test"),
        tool_response=tool_response,
    )

    output_text = "\n".join(call.args[0] for call in coder.io.tool_output.call_args_list)
    assert "example.txt" in output_text
    assert "alpha" in output_text
    coder.io.tool_error.assert_not_called()


def test_normalize_show_ops_joins_char_split_json_list():
    show_json = json.dumps(
        [{"file_path": "docs/ROADMAP.md", "start_text": "@000", "end_text": "\\n"}]
    )
    ops = normalize_show_ops(list(show_json))
    assert len(ops) == 1
    assert ops[0]["file_path"] == "docs/ROADMAP.md"
    assert ops[0]["start_text"] == "@000"


def _broken_readrange_show_json(*, file_path: str, start_text: str) -> str:
    """BrightVision dogfood: ReadRange show double-encoded with a newline after ':' ."""
    return (
        f'[{{"end_text":\n'
        f'", "file_path": "{file_path}", "start_text": "{start_text}"}}]'
    )


def test_normalize_show_ops_repairs_literal_newline_after_colon():
    broken = _broken_readrange_show_json(file_path="docs/ROADMAP.md", start_text="@000")
    ops = normalize_show_ops(broken)
    assert len(ops) == 1
    assert ops[0]["file_path"] == "docs/ROADMAP.md"
    assert ops[0]["start_text"] == "@000"
    assert ops[0]["end_text"] == ""


def test_format_output_repairs_broken_show_json_string(coder_with_file):
    """format_output must not fail JSON coercion when show is a broken JSON string."""
    coder, _file_path = coder_with_file
    broken_show = _broken_readrange_show_json(file_path="example.txt", start_text="alpha")
    args = json.dumps({"show": broken_show})
    tool_response = SimpleNamespace(function=SimpleNamespace(name="ReadRange", arguments=args))

    read_range.Tool.format_output(
        coder,
        mcp_server=SimpleNamespace(name="test"),
        tool_response=tool_response,
    )

    output_text = "\n".join(call.args[0] for call in coder.io.tool_output.call_args_list)
    assert "example.txt" in output_text
    assert "alpha" in output_text
    coder.io.tool_error.assert_not_called()
