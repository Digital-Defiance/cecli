"""
Background command management for cecli.

Provides a static BackgroundCommandManager class for running shell commands
in the background and capturing their output for injection into chat streams.
"""

import subprocess
import threading
from collections import deque
from typing import Dict, Optional, Tuple


class CircularBuffer:
    """
    Thread-safe circular buffer for storing command output with size limit.
    """

    def __init__(self, max_size: int = 4096):
        """
        Initialize circular buffer with maximum size.

        Args:
            max_size: Maximum number of characters to store
        """
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.Lock()
        self.total_added = 0  # Track total characters added for new output detection

    def append(self, text: str) -> None:
        """
        Add text to buffer, removing oldest content if exceeds max size.

        Args:
            text: Text to append to buffer
        """
        with self.lock:
            self.buffer.append(text)
            self.total_added += len(text)

    def get_all(self, clear: bool = False) -> str:
        """
        Get all content in buffer.

        Args:
            clear: If True, clear buffer after reading

        Returns:
            Concatenated string of all buffer content
        """
        with self.lock:
            result = "".join(self.buffer)
            if clear:
                self.buffer.clear()
                self.total_added = 0
            return result

    def get_new_output(self, last_read_position: int) -> Tuple[str, int]:
        """
        Get new output since last read position.

        Args:
            last_read_position: Position from last read (self.total_added value)

        Returns:
            Tuple of (new_output, new_position)
        """
        with self.lock:
            if last_read_position >= self.total_added:
                return "", self.total_added

            # Calculate how much new content we have
            new_chars = self.total_added - last_read_position
            # Get the last new_chars characters from the buffer
            all_content = "".join(self.buffer)
            new_output = all_content[-new_chars:] if new_chars > 0 else ""
            return new_output, self.total_added

    def clear(self) -> None:
        """Clear the buffer."""
        with self.lock:
            self.buffer.clear()
            self.total_added = 0

    def size(self) -> int:
        """Get current buffer size in characters."""
        with self.lock:
            return sum(len(chunk) for chunk in self.buffer)


class BackgroundProcess:
    """
    Represents a background process with output capture.
    """

    def __init__(self, command: str, process: subprocess.Popen, buffer: CircularBuffer):
        """
        Initialize background process wrapper.

        Args:
            command: Original command string
            process: Subprocess.Popen object
            buffer: CircularBuffer for output storage
        """
        self.command = command
        self.process = process
        self.buffer = buffer
        self.reader_thread = None
        self.last_read_position = 0
        self._start_output_reader()

    def _start_output_reader(self) -> None:
        """Start thread to read process output."""

        def reader():
            try:
                # Simple approach: read lines when available
                # This will block on readline(), but that's OK because
                # we're in a separate thread and the buffer will capture
                # output as soon as it's available

                # Read stdout
                for line in iter(self.process.stdout.readline, ""):
                    if line:
                        self.buffer.append(line)

                # Read stderr
                for line in iter(self.process.stderr.readline, ""):
                    if line:
                        self.buffer.append(line)

            except Exception as e:
                self.buffer.append(f"\n[Error reading process output: {str(e)}]\n")

        self.reader_thread = threading.Thread(target=reader, daemon=True)
        self.reader_thread.start()

    def get_output(self, clear: bool = False) -> str:
        """
        Get current output buffer.

        Args:
            clear: If True, clear buffer after reading

        Returns:
            Current output content
        """
        return self.buffer.get_all(clear)

    def get_new_output(self) -> str:
        """
        Get new output since last call.

        Returns:
            New output since last call
        """
        new_output, new_position = self.buffer.get_new_output(self.last_read_position)
        self.last_read_position = new_position
        return new_output

    def is_alive(self) -> bool:
        """Check if process is running."""
        return self.process.poll() is None

    def stop(self, timeout: float = 5.0) -> Tuple[bool, str, Optional[int]]:
        """
        Stop the process gracefully.

        Args:
            timeout: Seconds to wait for graceful termination

        Returns:
            Tuple of (success, output, exit_code)
        """
        try:
            # Try SIGTERM first
            self.process.terminate()
            self.process.wait(timeout=timeout)

            # Get final output
            output = self.get_output(clear=True)
            exit_code = self.process.returncode

            return True, output, exit_code

        except subprocess.TimeoutExpired:
            # Force kill if timeout
            self.process.kill()
            self.process.wait()

            output = self.get_output(clear=True)
            exit_code = self.process.returncode

            return True, output, exit_code

        except Exception as e:
            return False, f"Error stopping process: {str(e)}", None

    def wait(self, timeout: Optional[float] = None) -> Optional[int]:
        """
        Wait for process completion.

        Args:
            timeout: Timeout in seconds

        Returns:
            Exit code or None if timeout
        """
        try:
            self.process.wait(timeout=timeout)
            return self.process.returncode
        except subprocess.TimeoutExpired:
            return None


class BackgroundCommandManager:
    """
    Static manager for background commands with class-level storage.
    """

    # Class-level storage
    _background_commands: Dict[str, BackgroundProcess] = {}
    _lock = threading.Lock()
    _next_id = 1

    @classmethod
    def _generate_command_key(cls, command: str) -> str:
        """
        Generate a unique key for a command.

        Args:
            command: Command string

        Returns:
            Unique command key
        """
        with cls._lock:
            key = f"bg_{cls._next_id}_{hash(command) % 10000:04d}"
            cls._next_id += 1
            return key

    @classmethod
    def start_background_command(
        cls,
        command: str,
        verbose: bool = False,
        cwd: Optional[str] = None,
        max_buffer_size: int = 4096,
    ) -> str:
        """
        Start a command in background.

        Args:
            command: Shell command to execute
            verbose: Whether to print verbose output
            cwd: Working directory for command
            max_buffer_size: Maximum buffer size for output

        Returns:
            Command key for future reference
        """
        try:
            # Create output buffer
            buffer = CircularBuffer(max_size=max_buffer_size)

            # Start process with pipes for output capture
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,  # No stdin for background commands
                cwd=cwd,
                text=True,  # Use text mode for easier handling
                bufsize=1,  # Line buffered
                universal_newlines=True,
            )

            # Create background process wrapper
            bg_process = BackgroundProcess(command, process, buffer)

            # Generate unique key and store
            command_key = cls._generate_command_key(command)

            with cls._lock:
                cls._background_commands[command_key] = bg_process

            if verbose:
                print(f"[Background] Started command: {command} (key: {command_key})")

            return command_key

        except Exception as e:
            raise RuntimeError(f"Failed to start background command: {str(e)}")

    @classmethod
    def is_command_running(cls, command_key: str) -> bool:
        """
        Check if a background command is running.

        Args:
            command_key: Command key returned by start_background_command

        Returns:
            True if command is running
        """
        with cls._lock:
            bg_process = cls._background_commands.get(command_key)
            if not bg_process:
                return False
            return bg_process.is_alive()

    @classmethod
    def get_command_output(cls, command_key: str, clear: bool = False) -> str:
        """
        Get output from a background command.

        Args:
            command_key: Command key returned by start_background_command
            clear: If True, clear buffer after reading

        Returns:
            Command output
        """
        with cls._lock:
            bg_process = cls._background_commands.get(command_key)
            if not bg_process:
                return f"[Error] No background command found with key: {command_key}"
            return bg_process.get_output(clear)

    @classmethod
    def get_new_command_output(cls, command_key: str) -> str:
        """
        Get new output from a background command since last call.

        Args:
            command_key: Command key returned by start_background_command

        Returns:
            New command output since last call
        """
        with cls._lock:
            bg_process = cls._background_commands.get(command_key)
            if not bg_process:
                return f"[Error] No background command found with key: {command_key}"
            return bg_process.get_new_output()

    @classmethod
    def get_all_command_outputs(cls, clear: bool = False) -> Dict[str, str]:
        """
        Get output from all background commands (running or recently finished).

        Args:
            clear: If True, clear buffers after reading

        Returns:
            Dictionary mapping command keys to their output
        """
        with cls._lock:
            outputs = {}
            for command_key, bg_process in cls._background_commands.items():
                if clear:
                    output = bg_process.get_output(clear=True)
                else:
                    output = bg_process.get_new_output()
                if output.strip():
                    outputs[command_key] = output
            return outputs

    @classmethod
    def stop_background_command(cls, command_key: str) -> Tuple[bool, str, Optional[int]]:
        """
        Stop a running background command.

        Args:
            command_key: Command key returned by start_background_command

        Returns:
            Tuple of (success, output, exit_code)
        """
        with cls._lock:
            bg_process = cls._background_commands.get(command_key)
            if not bg_process:
                return False, f"No background command found with key: {command_key}", None

            # Stop the process
            success, output, exit_code = bg_process.stop()

            # Remove from tracking
            if command_key in cls._background_commands:
                del cls._background_commands[command_key]

            return success, output, exit_code

    @classmethod
    def stop_all_background_commands(cls) -> Dict[str, Tuple[bool, str, Optional[int]]]:
        """
        Stop all running background commands.

        Returns:
            Dictionary mapping command keys to (success, output, exit_code) tuples
        """
        results = {}
        with cls._lock:
            command_keys = list(cls._background_commands.keys())

        for command_key in command_keys:
            success, output, exit_code = cls.stop_background_command(command_key)
            results[command_key] = (success, output, exit_code)

        return results

    @classmethod
    def list_background_commands(cls) -> Dict[str, Dict[str, any]]:
        """
        List all background commands with their status.

        Returns:
            Dictionary with command information
        """
        with cls._lock:
            result = {}
            for command_key, bg_process in cls._background_commands.items():
                result[command_key] = {
                    "command": bg_process.command,
                    "running": bg_process.is_alive(),
                    "buffer_size": bg_process.buffer.size(),
                }
            return result
