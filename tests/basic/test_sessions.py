import os
import json
from pathlib import Path
import pytest
from unittest.mock import MagicMock, AsyncMock

from cecli.coders.agent_coder import AgentCoder
from cecli.coders.architect_coder import ArchitectCoder
from cecli.coders.ask_coder import AskCoder
from cecli.coders.base_coder import Coder
from cecli.sessions import SessionManager
from cecli.models import Model
from cecli.io import InputOutput


@pytest.fixture
def mock_coder():
    """Fixture to create a mock coder with necessary attributes."""
    coder = MagicMock()
    coder.abs_fnames = {"/path/to/file1.py"}
    coder.abs_read_only_fnames = {"/path/to/file2.py"}
    coder.abs_read_only_stubs_fnames = set()
    coder.auto_commits = True
    coder.auto_lint = True
    coder.auto_test = False
    coder.total_tokens_sent = 100
    coder.total_tokens_received = 200
    coder.total_cached_tokens = 50
    coder.total_cost = 0.01
    coder.edit_format = "diff"

    # Mock the main_model and its attributes
    main_model = MagicMock(spec=Model)
    main_model.name = "test_model"
    main_model.weak_model.name = "test_weak_model"
    main_model.editor_model.name = "test_editor_model"
    main_model.agent_model.name = "test_agent_model"
    main_model.editor_edit_format = "editor-diff"
    coder.main_model = main_model

    # Mock ConversationService methods
    mock_conversation_service = MagicMock()
    mock_conversation_service.get_manager.return_value.get_messages_dict.return_value = []
    coder.conversation_service = mock_conversation_service

    # Mock other necessary methods and attributes
    coder.get_rel_fname.side_effect = lambda x: os.path.basename(x)
    coder.abs_root_path.side_effect = lambda x: f"/test/root/{x}"
    coder.local_agent_folder.side_effect = lambda x: f".cecli/{x}"
    coder.io = MagicMock(spec=InputOutput)
    coder.io.read_text.return_value = "some todo content"

    return coder


@pytest.fixture
def session_manager(mock_coder):
    """Fixture to create a SessionManager instance."""
    return SessionManager(mock_coder, mock_coder.io)


def test_save_session(session_manager, mock_coder, tmp_path):
    """Test saving a session."""
    session_dir = tmp_path / ".cecli" / "sessions"
    os.makedirs(session_dir, exist_ok=True)
    mock_coder.abs_root_path.side_effect = lambda x: str(tmp_path / x)

    session_name = "test_session"
    success = session_manager.save_session(session_name, output=False)

    assert success
    session_file = session_dir / f"{session_name}.json"
    assert session_file.exists()

    with open(session_file, "r") as f:
        session_data = json.load(f)

    assert session_data["session_name"] == session_name
    assert session_data["model"] == "test_model"
    assert session_data["edit_format"] == "diff"
    assert "file1.py" in session_data["files"]["editable"]


@pytest.mark.asyncio
async def test_load_session_restores_edit_format(session_manager, mock_coder, tmp_path):
    """Test that loading a session restores the edit_format."""
    session_dir = tmp_path / ".cecli" / "sessions"
    os.makedirs(session_dir, exist_ok=True)
    mock_coder.abs_root_path.side_effect = lambda x: str(tmp_path / x)

    # 1. Save a session with a specific edit_format
    mock_coder.edit_format = "agent"
    session_name = "agent_session"
    session_manager.save_session(session_name, output=False)

    # 2. Change the coder's edit_format to something different
    mock_coder.edit_format = "diff"

    # 3. Load the session
    session_file = session_dir / f"{session_name}.json"

    # Mock the SwitchCoderSignal to capture the edit_format it's called with
    from cecli import commands
    original_switch_coder_signal = commands.SwitchCoderSignal

    class MockSwitchCoderSignal(Exception):
        def __init__(self, edit_format, **kwargs):
            self.edit_format = edit_format
            super().__init__()

    commands.SwitchCoderSignal = MockSwitchCoderSignal

    try:
        with pytest.raises(MockSwitchCoderSignal) as excinfo:
            await session_manager.load_session(str(session_file))

        # 4. Assert that the SwitchCoderSignal was raised with the correct edit_format
        assert excinfo.value.edit_format == "agent"

    finally:
        # Restore the original SwitchCoderSignal
        commands.SwitchCoderSignal = original_switch_coder_signal
