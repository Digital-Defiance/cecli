"""
Tests for background command management functionality.
"""

import sys
import types


def _install_stubs():
    """Install stub modules to avoid import errors during testing."""
    if "subprocess" not in sys.modules:
        subprocess_module = types.ModuleType("subprocess")

        class _DummyPopen:
            def __init__(self, *args, **kwargs):
                self.returncode = None
                self.stdout = _DummyPipe()
                self.stderr = _DummyPipe()
                self.stdin = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -1
                return None

            def kill(self):
                self.returncode = -2
                return None

            def wait(self, timeout=None):
                return self.returncode

        class _DummyPipe:
            def __init__(self):
                self.lines = []

            def readline(self):
                if self.lines:
                    return self.lines.pop(0)
                return ""

        subprocess_module.Popen = _DummyPopen
        subprocess_module.TimeoutExpired = Exception
        sys.modules["subprocess"] = subprocess_module


_install_stubs()

from cecli.helpers.background_commands import (  # noqa: E402
    BackgroundProcess,
    CircularBuffer,
)


def test_circular_buffer_basic_operations():
    """Test basic CircularBuffer operations: append, get_all, clear."""
    buffer = CircularBuffer(max_size=10)

    # Test append and get_all
    buffer.append("Hello")
    buffer.append(" ")
    buffer.append("World")

    assert buffer.get_all() == "Hello World"

    # Test clear
    buffer.clear()
    assert buffer.get_all() == ""
    assert buffer.size() == 0

    # Test that buffer is empty after clear
    buffer.append("New")
    assert buffer.get_all() == "New"


def test_circular_buffer_max_size():
    """Test that CircularBuffer respects max_size limit."""
    buffer = CircularBuffer(max_size=5)

    # Add content that exceeds max_size
    buffer.append("12345")  # Exactly max_size
    buffer.append("67890")  # This should push out "12345"

    # Buffer should contain both strings (2 elements, each 5 chars)
    # deque with maxlen=5 will keep up to 5 elements, not 5 characters
    assert buffer.get_all() == "1234567890"

    # Test with many small chunks
    buffer.clear()
    for i in range(10):
        buffer.append(str(i))

    # Should only keep last 5 elements: "5", "6", "7", "8", "9"
    assert buffer.get_all() == "56789"


def test_circular_buffer_get_new_output():
    """Test CircularBuffer.get_new_output method."""
    buffer = CircularBuffer(max_size=10)

    # Add some initial content
    buffer.append("Hello")
    buffer.append(" World")

    # Get new output from position 0 (should get everything)
    new_output, new_position = buffer.get_new_output(0)
    assert new_output == "Hello World"
    assert new_position == 11  # "Hello World" is 11 characters

    # Add more content
    buffer.append("!")

    # Get new output from previous position
    new_output, new_position = buffer.get_new_output(new_position)
    assert new_output == "!"
    assert new_position == 12

    # Try to get new output from current position (should be empty)
    new_output, new_position = buffer.get_new_output(new_position)
    assert new_output == ""
    assert new_position == 12


def test_background_process_basic():
    """Test basic BackgroundProcess functionality."""
    # Create a mock process

    class MockProcess:
        def __init__(self):
            self.returncode = None
            self.stdout = MockPipe(["Line 1\n", "Line 2\n"])
            self.stderr = MockPipe([])

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -1
            return None

        def kill(self):
            self.returncode = -2
            return None

        def wait(self, timeout=None):
            return self.returncode

    class MockPipe:
        def __init__(self, lines):
            self.lines = lines

        def readline(self):
            if self.lines:
                return self.lines.pop(0)
            return ""

    # Create BackgroundProcess
    buffer = CircularBuffer(max_size=100)
    process = MockProcess()
    bg_process = BackgroundProcess("test command", process, buffer)

    # Give reader thread a moment to read output
    import time

    time.sleep(0.1)

    # Check output
    output = bg_process.get_output()
    assert "Line 1" in output
    assert "Line 2" in output

    # Check is_alive
    assert bg_process.is_alive() is True

    # Stop the process
    # Note: stop() calls terminate() which sets returncode = -1 in our mock
    success, output, exit_code = bg_process.stop()
    assert success is True
    assert exit_code == -1  # terminate() sets returncode to -1 in MockProcess
