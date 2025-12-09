import shutil
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aider.tools import grep


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required")
def test_dash_prefixed_pattern_is_searched_literally(tmp_path):
    sample = tmp_path / "example.txt"
    sample.write_text("flag --prefix should be found\n")

    coder = SimpleNamespace(
        repo=SimpleNamespace(root=str(tmp_path)),
        io=SimpleNamespace(
            tool_error=Mock(),
            tool_output=Mock(),
            tool_warning=Mock(),
        ),
        verbose=False,
        root=str(tmp_path),
    )

    result = grep.Tool.execute(
        coder,
        pattern="--prefix",
        file_pattern="*.txt",
        directory=".",
        use_regex=False,
        case_insensitive=False,
        context_before=0,
        context_after=0,
    )

    assert "Found matches" in result
    assert "--prefix" in result
    coder.io.tool_error.assert_not_called()
