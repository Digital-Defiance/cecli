import asyncio
import json
import os
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import git
import pytest
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from aider.coders import Coder, CopyPasteCoder
from aider.commands import SwitchCoder
from aider.dump import dump  # noqa: F401
from aider.io import InputOutput
from aider.main import check_gitignore, load_dotenv_files, main, setup_git
from aider.utils import GitTemporaryDirectory, IgnorantTemporaryDirectory, make_repo


def mock_autosave_future():
    """Create an awaitable mock for _autosave_future.

    Returns AsyncMock()() - the first call creates an async mock function,
    the second call invokes it to get an awaitable coroutine object.
    """
    return AsyncMock()()


@pytest.fixture(autouse=True)
def test_env(request):
    """Autouse fixture providing test environment (replaces setUp/tearDown)."""
    # Setup (formerly setUp)
    original_env = os.environ.copy()
    os.environ["OPENAI_API_KEY"] = "deadbeef"
    os.environ["AIDER_CHECK_UPDATE"] = "false"
    os.environ["AIDER_ANALYTICS"] = "false"
    original_cwd = os.getcwd()
    tempdir_obj = IgnorantTemporaryDirectory()
    tempdir = tempdir_obj.name
    os.chdir(tempdir)
    # Fake home directory prevents tests from using the real ~/.aider.conf.yml file:
    homedir_obj = IgnorantTemporaryDirectory()
    os.environ["HOME"] = homedir_obj.name

    input_patcher = patch("builtins.input", return_value=None)
    mock_input = input_patcher.start()
    webbrowser_patcher = patch("aider.io.webbrowser.open")
    mock_webbrowser = webbrowser_patcher.start()

    # Make values available to tests via request.instance
    if request.instance:
        request.instance.tempdir = tempdir
        request.instance.tempdir_obj = tempdir_obj
        request.instance.homedir_obj = homedir_obj
        request.instance.original_env = original_env
        request.instance.original_cwd = original_cwd
        request.instance.mock_input = mock_input
        request.instance.mock_webbrowser = mock_webbrowser
        request.instance.input_patcher = input_patcher
        request.instance.webbrowser_patcher = webbrowser_patcher

    yield

    # Teardown (formerly tearDown)
    os.chdir(original_cwd)
    tempdir_obj.cleanup()
    homedir_obj.cleanup()
    os.environ.clear()
    os.environ.update(original_env)
    input_patcher.stop()
    webbrowser_patcher.stop()


@pytest.fixture
def dummy_io():
    """Provide DummyInput and DummyOutput for tests."""
    return {"input": DummyInput(), "output": DummyOutput()}


class TestMain:
    def test_main_with_empty_dir_no_files_on_command(self, dummy_io):
        main(["--no-git", "--exit", "--yes-always"], **dummy_io)

    def test_main_with_emptqy_dir_new_file(self, dummy_io):
        main(["foo.txt", "--yes-always", "--no-git", "--exit"], **dummy_io)
        assert os.path.exists("foo.txt")

    @patch("aider.repo.GitRepo.get_commit_message", return_value="mock commit message")
    def test_main_with_empty_git_dir_new_file(self, _, dummy_io):
        make_repo()
        main(["--yes-always", "foo.txt", "--exit"], **dummy_io)
        assert os.path.exists("foo.txt")

    @patch("aider.repo.GitRepo.get_commit_message", return_value="mock commit message")
    def test_main_with_empty_git_dir_new_files(self, _, dummy_io):
        make_repo()
        main(
            ["--yes-always", "foo.txt", "bar.txt", "--exit"],
            **dummy_io,
        )
        assert os.path.exists("foo.txt")
        assert os.path.exists("bar.txt")

    def test_main_with_dname_and_fname(self, dummy_io):
        subdir = Path("subdir")
        subdir.mkdir()
        make_repo(str(subdir))
        res = main(["subdir", "foo.txt"], **dummy_io)
        assert res is not None

    @patch("aider.repo.GitRepo.get_commit_message", return_value="mock commit message")
    def test_main_with_subdir_repo_fnames(self, _, dummy_io):
        subdir = Path("subdir")
        subdir.mkdir()
        make_repo(str(subdir))
        main(
            ["--yes-always", str(subdir / "foo.txt"), str(subdir / "bar.txt"), "--exit"],
            **dummy_io,
        )
        assert (subdir / "foo.txt").exists()
        assert (subdir / "bar.txt").exists()

    def test_main_copy_paste_model_overrides(self, dummy_io):
        overrides = json.dumps({"gpt-4o": {"fast": {"temperature": 0.42}}})
        coder = main(
            [
                "--no-git",
                "--exit",
                "--yes-always",
                "--model",
                "cp:gpt-4o:fast",
                "--model-overrides",
                overrides,
            ],
            **dummy_io,
            return_coder=True,
        )

        assert isinstance(coder, CopyPasteCoder)
        assert coder.main_model.copy_paste_mode
        assert coder.main_model.copy_paste_transport == "clipboard"
        assert coder.main_model.override_kwargs == {"temperature": 0.42}

    @patch("aider.main.ClipboardWatcher")
    def test_main_copy_paste_flag_sets_mode(self, mock_watcher, dummy_io):
        mock_watcher.return_value = MagicMock()

        coder = main(
            ["--no-git", "--exit", "--yes-always", "--copy-paste"],
            **dummy_io,
            return_coder=True,
        )

        assert not isinstance(coder, CopyPasteCoder)
        assert coder.main_model.copy_paste_mode
        assert coder.main_model.copy_paste_transport == "api"
        assert coder.copy_paste_mode
        assert not coder.manual_copy_paste

    def test_main_with_git_config_yml(self, dummy_io):
        make_repo()

        Path(".aider.conf.yml").write_text("auto-commits: false\n")
        with patch("aider.coders.Coder.create") as MockCoder:
            mock_coder_instance = MockCoder.return_value
            mock_coder_instance._autosave_future = mock_autosave_future()
            main(["--yes-always"], **dummy_io)
            _, kwargs = MockCoder.call_args
            assert kwargs["auto_commits"] is False

        Path(".aider.conf.yml").write_text("auto-commits: true\n")
        with patch("aider.coders.Coder.create") as MockCoder:
            mock_coder_instance = MockCoder.return_value
            mock_coder_instance._autosave_future = mock_autosave_future()
            main([], **dummy_io)
            _, kwargs = MockCoder.call_args
            assert kwargs["auto_commits"] is True

    def test_main_with_empty_git_dir_new_subdir_file(self, dummy_io):
        make_repo()
        subdir = Path("subdir")
        subdir.mkdir()
        fname = subdir / "foo.txt"
        fname.touch()
        subprocess.run(["git", "add", str(subdir)])
        subprocess.run(["git", "commit", "-m", "added"])

        # This will throw a git error on windows if get_tracked_files doesn't
        # properly convert git/posix/paths to git\posix\paths.
        # Because aider will try and `git add` a file that's already in the repo.
        main(["--yes-always", str(fname), "--exit"], **dummy_io)

    def test_setup_git(self, dummy_io):
        io = InputOutput(pretty=False, yes=True)
        git_root = asyncio.run(setup_git(None, io))
        git_root = Path(git_root).resolve()
        assert git_root == Path(self.tempdir).resolve()

        assert git.Repo(self.tempdir)

        gitignore = Path.cwd() / ".gitignore"
        assert gitignore.exists()
        assert ".aider*" == gitignore.read_text().splitlines()[0]

    def test_check_gitignore(self, dummy_io):
        with GitTemporaryDirectory():
            os.environ["GIT_CONFIG_GLOBAL"] = "globalgitconfig"

            io = InputOutput(pretty=False, yes=True)
            cwd = Path.cwd()
            gitignore = cwd / ".gitignore"

            assert not gitignore.exists()
            asyncio.run(check_gitignore(cwd, io))
            assert gitignore.exists()

            assert ".aider*" == gitignore.read_text().splitlines()[0]

            # Test without .env file present
            gitignore.write_text("one\ntwo\n")
            asyncio.run(check_gitignore(cwd, io))
            assert "one\ntwo\n.aider*\n" == gitignore.read_text()

            # Test with .env file present
            env_file = cwd / ".env"
            env_file.touch()
            asyncio.run(check_gitignore(cwd, io))
            assert "one\ntwo\n.aider*\n.env\n" == gitignore.read_text()
            del os.environ["GIT_CONFIG_GLOBAL"]

    def test_command_line_gitignore_files_flag(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)

            # Create a .gitignore file
            gitignore_file = git_dir / ".gitignore"
            gitignore_file.write_text("ignored.txt\n")

            # Create an ignored file
            ignored_file = git_dir / "ignored.txt"
            ignored_file.write_text("This file should be ignored.")

            # Get the absolute path to the ignored file
            abs_ignored_file = str(ignored_file.resolve())

            # Test without the --add-gitignore-files flag (default: False)
            coder = main(
                ["--exit", "--yes-always", abs_ignored_file],
                **dummy_io,
                return_coder=True,
                force_git_root=git_dir,
            )
            # Verify the ignored file is not in the chat
            assert abs_ignored_file not in coder.abs_fnames

            # Test with --add-gitignore-files set to True
            coder = main(
                ["--add-gitignore-files", "--exit", "--yes-always", abs_ignored_file],
                **dummy_io,
                return_coder=True,
                force_git_root=git_dir,
            )
            # Verify the ignored file is in the chat
            assert abs_ignored_file in coder.abs_fnames

            # Test with --add-gitignore-files set to False
            coder = main(
                ["--no-add-gitignore-files", "--exit", "--yes-always", abs_ignored_file],
                **dummy_io,
                return_coder=True,
                force_git_root=git_dir,
            )
            # Verify the ignored file is not in the chat
            assert abs_ignored_file not in coder.abs_fnames

    def test_add_command_gitignore_files_flag(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)

            # Create a .gitignore file
            gitignore_file = git_dir / ".gitignore"
            gitignore_file.write_text("ignored.txt\n")

            # Create an ignored file
            ignored_file = git_dir / "ignored.txt"
            ignored_file.write_text("This file should be ignored.")

            # Get the absolute path to the ignored file
            abs_ignored_file = str(ignored_file.resolve())
            rel_ignored_file = "ignored.txt"

            # Test without the --add-gitignore-files flag (default: False)
            coder = main(
                ["--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
                force_git_root=git_dir,
            )

            try:
                asyncio.run(coder.commands.do_run("add", rel_ignored_file))
            except SwitchCoder:
                pass

            # Verify the ignored file is not in the chat
            assert abs_ignored_file not in coder.abs_fnames

            # Test with --add-gitignore-files set to True
            coder = main(
                ["--add-gitignore-files", "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
                force_git_root=git_dir,
            )
            try:
                asyncio.run(coder.commands.do_run("add", rel_ignored_file))
            except SwitchCoder:
                pass

            # Verify the ignored file is in the chat
            assert abs_ignored_file in coder.abs_fnames

            # Test with --add-gitignore-files set to False
            coder = main(
                ["--no-add-gitignore-files", "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
                force_git_root=git_dir,
            )

            try:
                asyncio.run(coder.commands.do_run("add", rel_ignored_file))
            except SwitchCoder:
                pass

            # Verify the ignored file is not in the chat
            assert abs_ignored_file not in coder.abs_fnames

    @pytest.mark.parametrize(
        "args,expected_kwargs",
        [
            (["--no-auto-commits", "--yes-always"], {"auto_commits": False}),
            (["--auto-commits", "--no-git"], {"auto_commits": True}),
            (["--no-git"], {"dirty_commits": True, "auto_commits": True}),
            (["--no-dirty-commits", "--no-git"], {"dirty_commits": False}),
            (["--dirty-commits", "--no-git"], {"dirty_commits": True}),
        ],
        ids=["no_auto_commits", "auto_commits", "defaults", "no_dirty_commits", "dirty_commits"],
    )
    def test_main_args(self, args, expected_kwargs, dummy_io):
        with patch("aider.coders.Coder.create") as MockCoder:
            mock_coder_instance = MockCoder.return_value
            mock_coder_instance._autosave_future = mock_autosave_future()
            main(args, input=DummyInput())
            _, kwargs = MockCoder.call_args
            for key, expected_value in expected_kwargs.items():
                assert kwargs[key] is expected_value

    def test_env_file_override(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)
            git_env = git_dir / ".env"

            fake_home = git_dir / "fake_home"
            fake_home.mkdir()
            os.environ["HOME"] = str(fake_home)
            home_env = fake_home / ".env"

            cwd = git_dir / "subdir"
            cwd.mkdir()
            os.chdir(cwd)
            cwd_env = cwd / ".env"

            named_env = git_dir / "named.env"

            os.environ["E"] = "existing"
            home_env.write_text("A=home\nB=home\nC=home\nD=home")
            git_env.write_text("A=git\nB=git\nC=git")
            cwd_env.write_text("A=cwd\nB=cwd")
            named_env.write_text("A=named")

            with patch("pathlib.Path.home", return_value=fake_home):
                main(["--yes-always", "--exit", "--env-file", str(named_env)])

            assert os.environ["A"] == "named"
            assert os.environ["B"] == "cwd"
            assert os.environ["C"] == "git"
            assert os.environ["D"] == "home"
            assert os.environ["E"] == "existing"

    def test_message_file_flag(self, dummy_io):
        message_file_content = "This is a test message from a file."
        message_file_path = tempfile.mktemp()
        with open(message_file_path, "w", encoding="utf-8") as message_file:
            message_file.write(message_file_content)

        # Create a mock async function for the run method
        async def mock_run(*args, **kwargs):
            pass

        with patch("aider.coders.Coder.create") as MockCoder:
            # Create a mock coder instance with an async run method
            mock_coder_instance = MagicMock()
            mock_coder_instance.run = AsyncMock()
            mock_coder_instance._autosave_future = mock_autosave_future()
            MockCoder.return_value = mock_coder_instance

            main(
                ["--yes-always", "--message-file", message_file_path],
                **dummy_io,
            )
            # Check that run was called with the correct message
            mock_coder_instance.run.assert_called_once_with(with_message=message_file_content)

        os.remove(message_file_path)

    def test_encodings_arg(self, dummy_io):
        fname = "foo.py"

        with GitTemporaryDirectory():
            with patch("aider.coders.Coder.create") as MockCoder:
                mock_coder_instance = MockCoder.return_value
                mock_coder_instance._autosave_future = mock_autosave_future()
                with patch("aider.main.InputOutput") as MockSend:

                    def side_effect(*args, **kwargs):
                        assert kwargs["encoding"] == "iso-8859-15"
                        mock_io = MagicMock()
                        mock_io.confirm_ask = AsyncMock(return_value=True)
                        return mock_io

                    MockSend.side_effect = side_effect

                    main(["--yes-always", fname, "--encoding", "iso-8859-15"])

    def test_main_exit_calls_version_check(self, dummy_io):
        with GitTemporaryDirectory():
            with (
                patch("aider.main.check_version") as mock_check_version,
                patch("aider.main.InputOutput") as mock_input_output,
            ):
                mock_input_output.return_value.confirm_ask = AsyncMock(return_value=True)
                main(["--exit", "--check-update"], **dummy_io)
                mock_check_version.assert_called_once()
                mock_input_output.assert_called_once()

    @patch("aider.main.InputOutput", autospec=True)
    @patch("aider.coders.base_coder.Coder.run")
    def test_main_message_adds_to_input_history(self, mock_run, MockInputOutput, dummy_io):
        test_message = "test message"
        mock_io_instance = MockInputOutput.return_value
        mock_io_instance.pretty = True

        main(["--message", test_message], **dummy_io)

        mock_io_instance.add_to_input_history.assert_called_once_with(test_message)

    @patch("aider.main.InputOutput", autospec=True)
    @patch("aider.coders.base_coder.Coder.run")
    def test_yes(self, mock_run, MockInputOutput, dummy_io):
        test_message = "test message"
        MockInputOutput.return_value.pretty = True

        main(["--yes-always", "--message", test_message])
        args, kwargs = MockInputOutput.call_args
        assert args[1]

    @patch("aider.main.InputOutput", autospec=True)
    @patch("aider.coders.base_coder.Coder.run")
    def test_default_yes(self, mock_run, MockInputOutput, dummy_io):
        test_message = "test message"
        MockInputOutput.return_value.pretty = True

        main(["--message", test_message])
        args, kwargs = MockInputOutput.call_args
        assert args[1] is None

    @pytest.mark.parametrize(
        "mode_flag,expected_theme",
        [
            ("--dark-mode", "monokai"),
            ("--light-mode", "default"),
        ],
        ids=["dark_mode", "light_mode"],
    )
    def test_mode_sets_code_theme(self, mode_flag, expected_theme, dummy_io):
        # Mock InputOutput to capture the configuration
        with patch("aider.main.InputOutput") as MockInputOutput:
            MockInputOutput.return_value.get_input.return_value = None
            main([mode_flag, "--no-git", "--exit"], **dummy_io)
            # Ensure InputOutput was called
            MockInputOutput.assert_called_once()
            # Check if the code_theme setting matches expected
            _, kwargs = MockInputOutput.call_args
            assert kwargs["code_theme"] == expected_theme

    def create_env_file(self, file_name, content):
        env_file_path = Path(self.tempdir) / file_name
        env_file_path.write_text(content)
        return env_file_path

    def test_env_file_flag_sets_automatic_variable(self, dummy_io):
        env_file_path = self.create_env_file(".env.test", "AIDER_DARK_MODE=True")
        with patch("aider.main.InputOutput") as MockInputOutput:
            MockInputOutput.return_value.get_input.return_value = None
            MockInputOutput.return_value.get_input.confirm_ask = True
            main(
                ["--env-file", str(env_file_path), "--no-git", "--exit"],
                **dummy_io,
            )
            MockInputOutput.assert_called_once()
            # Check if the color settings are for dark mode
            _, kwargs = MockInputOutput.call_args
            assert kwargs["code_theme"] == "monokai"

    def test_default_env_file_sets_automatic_variable(self, dummy_io):
        self.create_env_file(".env", "AIDER_DARK_MODE=True")
        with patch("aider.main.InputOutput") as MockInputOutput:
            MockInputOutput.return_value.get_input.return_value = None
            MockInputOutput.return_value.get_input.confirm_ask = True
            main(["--no-git", "--exit"], **dummy_io)
            # Ensure InputOutput was called
            MockInputOutput.assert_called_once()
            # Check if the color settings are for dark mode
            _, kwargs = MockInputOutput.call_args
            assert kwargs["code_theme"] == "monokai"

    def test_false_vals_in_env_file(self, dummy_io):
        self.create_env_file(".env", "AIDER_SHOW_DIFFS=off")
        with patch("aider.coders.Coder.create", autospec=True) as MockCoder:
            mock_coder_instance = MockCoder.return_value
            mock_coder_instance._autosave_future = mock_autosave_future()
            main(["--no-git", "--yes-always"], **dummy_io)
            MockCoder.assert_called_once()
            _, kwargs = MockCoder.call_args
            assert kwargs["show_diffs"] is False

    def test_true_vals_in_env_file(self, dummy_io):
        self.create_env_file(".env", "AIDER_SHOW_DIFFS=on")
        with patch("aider.coders.Coder.create") as MockCoder:
            mock_coder_instance = MockCoder.return_value
            mock_coder_instance._autosave_future = mock_autosave_future()
            main(["--no-git", "--yes-always"], **dummy_io)
            MockCoder.assert_called_once()
            _, kwargs = MockCoder.call_args
            assert kwargs["show_diffs"] is True

    def test_lint_option(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            # Create a dirty file in the root
            dirty_file = Path("dirty_file.py")
            dirty_file.write_text("def foo():\n    return 'bar'")

            repo = git.Repo(".")
            repo.git.add(str(dirty_file))
            repo.git.commit("-m", "new")

            dirty_file.write_text("def foo():\n    return '!!!!!'")

            # Create a subdirectory
            subdir = Path(git_dir) / "subdir"
            subdir.mkdir()

            # Change to the subdirectory
            os.chdir(subdir)

            # Mock the Linter class
            with patch("aider.linter.Linter.lint") as MockLinter:
                MockLinter.return_value = ""

                # Run main with --lint option
                main(["--lint", "--yes-always"], **dummy_io)

                # Check if the Linter was called with a filename ending in "dirty_file.py"
                # but not ending in "subdir/dirty_file.py"
                MockLinter.assert_called_once()
                called_arg = MockLinter.call_args[0][0]
                assert called_arg.endswith("dirty_file.py")
                assert not called_arg.endswith(f"subdir{os.path.sep}dirty_file.py")

    def test_lint_option_with_explicit_files(self, dummy_io):
        with GitTemporaryDirectory():
            # Create two files
            file1 = Path("file1.py")
            file1.write_text("def foo(): pass")
            file2 = Path("file2.py")
            file2.write_text("def bar(): pass")

            # Mock the Linter class
            with patch("aider.linter.Linter.lint") as MockLinter:
                MockLinter.return_value = ""

                # Run main with --lint and explicit files
                main(
                    ["--lint", "file1.py", "file2.py", "--yes-always"],
                    **dummy_io,
                )

                # Check if the Linter was called twice (once for each file)
                assert MockLinter.call_count == 2

                # Check that both files were linted
                called_files = [call[0][0] for call in MockLinter.call_args_list]
                assert any(f.endswith("file1.py") for f in called_files)
                assert any(f.endswith("file2.py") for f in called_files)

    def test_lint_option_with_glob_pattern(self, dummy_io):
        with GitTemporaryDirectory():
            # Create multiple Python files
            file1 = Path("test1.py")
            file1.write_text("def foo(): pass")
            file2 = Path("test2.py")
            file2.write_text("def bar(): pass")
            file3 = Path("readme.txt")
            file3.write_text("not a python file")

            # Mock the Linter class
            with patch("aider.linter.Linter.lint") as MockLinter:
                MockLinter.return_value = ""

                # Run main with --lint and glob pattern
                main(
                    ["--lint", "test*.py", "--yes-always"],
                    **dummy_io,
                )

                # Check if the Linter was called for Python files matching the glob
                assert MockLinter.call_count >= 2

                # Check that Python files were linted
                called_files = [call[0][0] for call in MockLinter.call_args_list]
                assert any(f.endswith("test1.py") for f in called_files)
                assert any(f.endswith("test2.py") for f in called_files)
                # Check that non-Python file was not linted
                assert not any(f.endswith("readme.txt") for f in called_files)

    def test_verbose_mode_lists_env_vars(self, dummy_io):
        self.create_env_file(".env", "AIDER_DARK_MODE=on")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(
                ["--no-git", "--verbose", "--exit", "--yes-always"],
                **dummy_io,
            )
            output = mock_stdout.getvalue()
            relevant_output = "\n".join(
                line
                for line in output.splitlines()
                if "AIDER_DARK_MODE" in line or "dark_mode" in line
            )  # this bit just helps failing assertions to be easier to read
            assert "AIDER_DARK_MODE" in relevant_output
            assert "dark_mode" in relevant_output
            import re

            assert re.search(r"AIDER_DARK_MODE:\s+on", relevant_output)
            assert re.search(r"dark_mode:\s+True", relevant_output)

    def test_yaml_config_file_loading(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)

            # Create fake home directory
            fake_home = git_dir / "fake_home"
            fake_home.mkdir()
            os.environ["HOME"] = str(fake_home)

            # Create subdirectory as current working directory
            cwd = git_dir / "subdir"
            cwd.mkdir()
            os.chdir(cwd)

            # Create .aider.conf.yml files in different locations
            home_config = fake_home / ".aider.conf.yml"
            git_config = git_dir / ".aider.conf.yml"
            cwd_config = cwd / ".aider.conf.yml"
            named_config = git_dir / "named.aider.conf.yml"

            cwd_config.write_text("model: gpt-4-32k\nmap-tokens: 4096\n")
            git_config.write_text("model: gpt-4\nmap-tokens: 2048\n")
            home_config.write_text("model: gpt-3.5-turbo\nmap-tokens: 1024\n")
            named_config.write_text("model: gpt-4-1106-preview\nmap-tokens: 8192\n")

            with (
                patch("pathlib.Path.home", return_value=fake_home),
                patch("aider.coders.Coder.create") as MockCoder,
            ):
                mock_coder_instance = MockCoder.return_value
                mock_coder_instance._autosave_future = mock_autosave_future()
                # Test loading from specified config file
                main(
                    ["--yes-always", "--exit", "--config", str(named_config)],
                    **dummy_io,
                )
                _, kwargs = MockCoder.call_args
                assert kwargs["main_model"].name == "gpt-4-1106-preview"
                assert kwargs["map_tokens"] == 8192

                # Test loading from current working directory
                mock_coder_instance._autosave_future = mock_autosave_future()
                main(["--yes-always", "--exit"], **dummy_io)
                _, kwargs = MockCoder.call_args
                print("kwargs:", kwargs)  # Add this line for debugging
                assert "main_model" in kwargs, "main_model key not found in kwargs"
                assert kwargs["main_model"].name == "gpt-4-32k"
                assert kwargs["map_tokens"] == 4096

                # Test loading from git root
                cwd_config.unlink()
                mock_coder_instance._autosave_future = mock_autosave_future()
                main(["--yes-always", "--exit"], **dummy_io)
                _, kwargs = MockCoder.call_args
                assert kwargs["main_model"].name == "gpt-4"
                assert kwargs["map_tokens"] == 2048

                # Test loading from home directory
                git_config.unlink()
                mock_coder_instance._autosave_future = mock_autosave_future()
                main(["--yes-always", "--exit"], **dummy_io)
                _, kwargs = MockCoder.call_args
                assert kwargs["main_model"].name == "gpt-3.5-turbo"
                assert kwargs["map_tokens"] == 1024

    def test_map_tokens_option(self, dummy_io):
        with GitTemporaryDirectory():
            with patch("aider.coders.base_coder.RepoMap") as MockRepoMap:
                MockRepoMap.return_value.max_map_tokens = 0
                main(
                    ["--model", "gpt-4", "--map-tokens", "0", "--exit", "--yes-always"],
                    **dummy_io,
                )
                MockRepoMap.assert_not_called()

    def test_map_tokens_option_with_non_zero_value(self, dummy_io):
        with GitTemporaryDirectory():
            with patch("aider.coders.base_coder.RepoMap") as MockRepoMap:
                MockRepoMap.return_value.max_map_tokens = 1000
                main(
                    ["--model", "gpt-4", "--map-tokens", "1000", "--exit", "--yes-always"],
                    **dummy_io,
                )
                MockRepoMap.assert_called_once()

    def test_read_option(self, dummy_io):
        with GitTemporaryDirectory():
            test_file = "test_file.txt"
            Path(test_file).touch()

            coder = main(
                ["--read", test_file, "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )

            assert str(Path(test_file).resolve()) in coder.abs_read_only_fnames

    def test_read_option_with_external_file(self, dummy_io):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as external_file:
            external_file.write("External file content")
            external_file_path = external_file.name

        try:
            with GitTemporaryDirectory():
                coder = main(
                    ["--read", external_file_path, "--exit", "--yes-always"],
                    **dummy_io,
                    return_coder=True,
                )

                real_external_file_path = os.path.realpath(external_file_path)
                assert real_external_file_path in coder.abs_read_only_fnames
        finally:
            os.unlink(external_file_path)

    def test_model_metadata_file(self, dummy_io):
        # Re-init so we don't have old data lying around from earlier test cases
        from aider import models

        models.model_info_manager = models.ModelInfoManager()

        from aider.llm import litellm

        litellm._lazy_module = None

        with GitTemporaryDirectory():
            metadata_file = Path(".aider.model.metadata.json")

            # must be a fully qualified model name: provider/...
            metadata_content = {"deepseek/deepseek-chat": {"max_input_tokens": 1234}}
            metadata_file.write_text(json.dumps(metadata_content))

            coder = main(
                [
                    "--model",
                    "deepseek/deepseek-chat",
                    "--model-metadata-file",
                    str(metadata_file),
                    "--exit",
                    "--yes-always",
                ],
                **dummy_io,
                return_coder=True,
            )

            assert coder.main_model.info["max_input_tokens"] == 1234

    def test_sonnet_and_cache_options(self, dummy_io):
        with GitTemporaryDirectory():
            with patch("aider.coders.base_coder.RepoMap") as MockRepoMap:
                mock_repo_map = MagicMock()
                mock_repo_map.max_map_tokens = 1000  # Set a specific value
                MockRepoMap.return_value = mock_repo_map

                main(
                    ["--sonnet", "--cache-prompts", "--exit", "--yes-always"],
                    **dummy_io,
                )

                MockRepoMap.assert_called_once()
                call_args, call_kwargs = MockRepoMap.call_args
                assert call_kwargs.get("refresh") == "files"  # Check the 'refresh' keyword argument

    def test_sonnet_and_cache_prompts_options(self, dummy_io):
        with GitTemporaryDirectory():
            coder = main(
                ["--sonnet", "--cache-prompts", "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )

            assert coder.add_cache_headers

    def test_4o_and_cache_options(self, dummy_io):
        with GitTemporaryDirectory():
            coder = main(
                ["--4o", "--cache-prompts", "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )

            assert not coder.add_cache_headers

    def test_return_coder(self, dummy_io):
        with GitTemporaryDirectory():
            result = main(
                ["--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )
            assert isinstance(result, Coder)

            result = main(
                ["--exit", "--yes-always"],
                **dummy_io,
                return_coder=False,
            )
            assert result == 0

    def test_map_mul_option(self, dummy_io):
        with GitTemporaryDirectory():
            coder = main(
                ["--map-mul", "5", "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )
            assert isinstance(coder, Coder)
            assert coder.repo_map.map_mul_no_files == 5

    @pytest.mark.parametrize(
        "flag_arg,attr_name,expected",
        [
            (None, "suggest_shell_commands", True),
            ("--no-suggest-shell-commands", "suggest_shell_commands", False),
            ("--suggest-shell-commands", "suggest_shell_commands", True),
            (None, "detect_urls", True),
            ("--no-detect-urls", "detect_urls", False),
            ("--detect-urls", "detect_urls", True),
        ],
        ids=[
            "suggest_default",
            "suggest_disabled",
            "suggest_enabled",
            "urls_default",
            "urls_disabled",
            "urls_enabled",
        ],
    )
    def test_boolean_flags(self, flag_arg, attr_name, expected, dummy_io):
        with GitTemporaryDirectory():
            args = ["--exit", "--yes-always"]
            if flag_arg:
                args.insert(0, flag_arg)
            coder = main(args, **dummy_io, return_coder=True)
            assert getattr(coder, attr_name) == expected

    def test_accepts_settings_warnings(self, dummy_io):
        # Test that appropriate warnings are shown based on accepts_settings configuration
        with GitTemporaryDirectory():
            # Test model that accepts the thinking_tokens setting
            with (
                patch("aider.io.InputOutput.tool_warning") as mock_warning,
                patch("aider.models.Model.set_thinking_tokens") as mock_set_thinking,
            ):
                main(
                    [
                        "--model",
                        "anthropic/claude-3-7-sonnet-20250219",
                        "--thinking-tokens",
                        "1000",
                        "--yes-always",
                        "--exit",
                    ],
                    **dummy_io,
                )
                # No warning should be shown as this model accepts thinking_tokens
                for call in mock_warning.call_args_list:
                    assert "thinking_tokens" not in call[0][0]
                # Method should be called
                mock_set_thinking.assert_called_once_with("1000")

            # Test model that doesn't have accepts_settings for thinking_tokens
            with (
                patch("aider.io.InputOutput.tool_warning") as mock_warning,
                patch("aider.models.Model.set_thinking_tokens") as mock_set_thinking,
            ):
                main(
                    [
                        "--model",
                        "gpt-4o",
                        "--thinking-tokens",
                        "1000",
                        "--check-model-accepts-settings",
                        "--yes-always",
                        "--exit",
                    ],
                    **dummy_io,
                )
                # Warning should be shown
                warning_shown = False
                for call in mock_warning.call_args_list:
                    if "thinking_tokens" in call[0][0]:
                        warning_shown = True
                assert warning_shown
                # Method should NOT be called because model doesn't support it and check flag is on
                mock_set_thinking.assert_not_called()

            # Test model that accepts the reasoning_effort setting
            with (
                patch("aider.io.InputOutput.tool_warning") as mock_warning,
                patch("aider.models.Model.set_reasoning_effort") as mock_set_reasoning,
            ):
                main(
                    ["--model", "o1", "--reasoning-effort", "3", "--yes-always", "--exit"],
                    **dummy_io,
                )
                # No warning should be shown as this model accepts reasoning_effort
                for call in mock_warning.call_args_list:
                    assert "reasoning_effort" not in call[0][0]
                # Method should be called
                mock_set_reasoning.assert_called_once_with("3")

            # Test model that doesn't have accepts_settings for reasoning_effort
            with (
                patch("aider.io.InputOutput.tool_warning") as mock_warning,
                patch("aider.models.Model.set_reasoning_effort") as mock_set_reasoning,
            ):
                main(
                    [
                        "--model",
                        "gpt-3.5-turbo",
                        "--reasoning-effort",
                        "3",
                        "--yes-always",
                        "--exit",
                    ],
                    **dummy_io,
                )
                # Warning should be shown
                warning_shown = False
                for call in mock_warning.call_args_list:
                    if "reasoning_effort" in call[0][0]:
                        warning_shown = True
                assert warning_shown
                # Method should still be called by default
                mock_set_reasoning.assert_not_called()

    @patch("aider.models.ModelInfoManager.set_verify_ssl")
    def test_no_verify_ssl_sets_model_info_manager(self, mock_set_verify_ssl, dummy_io):
        with GitTemporaryDirectory():
            # Mock Model class to avoid actual model initialization
            with patch("aider.models.Model") as mock_model:
                # Configure the mock to avoid the TypeError
                mock_model.return_value.info = {}
                mock_model.return_value.name = "gpt-4"  # Add a string name
                mock_model.return_value.validate_environment.return_value = {
                    "missing_keys": [],
                    "keys_in_environment": [],
                }

                # Mock fuzzy_match_models to avoid string operations on MagicMock
                with patch("aider.models.fuzzy_match_models", return_value=[]):
                    main(
                        ["--no-verify-ssl", "--exit", "--yes-always"],
                        **dummy_io,
                    )
                mock_set_verify_ssl.assert_called_once_with(False)

    def test_pytest_env_vars(self, dummy_io):
        # Verify that environment variables from pytest.ini are properly set
        assert os.environ.get("AIDER_ANALYTICS") == "false"

    @pytest.mark.parametrize(
        "set_env_args,expected_env,expected_result",
        [
            (
                ["--set-env", "TEST_VAR=test_value"],
                {"TEST_VAR": "test_value"},
                None,
            ),
            (
                ["--set-env", "TEST_VAR1=value1", "--set-env", "TEST_VAR2=value2"],
                {"TEST_VAR1": "value1", "TEST_VAR2": "value2"},
                None,
            ),
            (
                ["--set-env", "TEST_VAR=test value with spaces"],
                {"TEST_VAR": "test value with spaces"},
                None,
            ),
            (
                ["--set-env", "INVALID_FORMAT"],
                {},
                1,
            ),
        ],
        ids=["single", "multiple", "with_spaces", "invalid_format"],
    )
    def test_set_env(self, set_env_args, expected_env, expected_result, dummy_io):
        with GitTemporaryDirectory():
            args = set_env_args + ["--exit", "--yes-always"]
            result = main(args)
            if expected_result is not None:
                assert result == expected_result
            for env_var, expected_value in expected_env.items():
                assert os.environ.get(env_var) == expected_value

    @pytest.mark.parametrize(
        "api_key_args,expected_env,expected_result",
        [
            (
                ["--api-key", "anthropic=test-key"],
                {"ANTHROPIC_API_KEY": "test-key"},
                None,
            ),
            (
                ["--api-key", "anthropic=key1", "--api-key", "openai=key2"],
                {"ANTHROPIC_API_KEY": "key1", "OPENAI_API_KEY": "key2"},
                None,
            ),
            (
                ["--api-key", "INVALID_FORMAT"],
                {},
                1,
            ),
        ],
        ids=["single", "multiple", "invalid_format"],
    )
    def test_api_key(self, api_key_args, expected_env, expected_result, dummy_io):
        with GitTemporaryDirectory():
            args = api_key_args + ["--exit", "--yes-always"]
            result = main(args)
            if expected_result is not None:
                assert result == expected_result
            for env_var, expected_value in expected_env.items():
                assert os.environ.get(env_var) == expected_value

    def test_git_config_include(self, dummy_io):
        # Test that aider respects git config includes for user.name and user.email
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)

            # Create an includable config file with user settings
            include_config = git_dir / "included.gitconfig"
            include_config.write_text(
                "[user]\n    name = Included User\n    email = included@example.com\n"
            )

            # Set up main git config to include the other file
            repo = git.Repo(git_dir)
            include_path = str(include_config).replace("\\", "/")
            repo.git.config("--local", "include.path", str(include_path))

            # Verify the config is set up correctly using git command
            assert repo.git.config("user.name") == "Included User"
            assert repo.git.config("user.email") == "included@example.com"

            # Manually check the git config file to confirm include directive
            git_config_path = git_dir / ".git" / "config"
            git_config_content = git_config_path.read_text()

            # Run aider and verify it doesn't change the git config
            main(["--yes-always", "--exit"], **dummy_io)

            # Check that the user settings are still the same using git command
            repo = git.Repo(git_dir)  # Re-open repo to ensure we get fresh config
            assert repo.git.config("user.name") == "Included User"
            assert repo.git.config("user.email") == "included@example.com"

            # Manually check the git config file again to ensure it wasn't modified
            git_config_content_after = git_config_path.read_text()
            assert git_config_content == git_config_content_after

    def test_git_config_include_directive(self, dummy_io):
        # Test that aider respects the include directive in git config
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)

            # Create an includable config file with user settings
            include_config = git_dir / "included.gitconfig"
            include_config.write_text(
                "[user]\n    name = Directive User\n    email = directive@example.com\n"
            )

            # Set up main git config with include directive
            git_config = git_dir / ".git" / "config"
            # Use normalized path with forward slashes for git config
            include_path = str(include_config).replace("\\", "/")
            with open(git_config, "a") as f:
                f.write(f"\n[include]\n    path = {include_path}\n")

            # Read the modified config file
            modified_config_content = git_config.read_text()

            # Verify the include directive was added correctly
            assert "[include]" in modified_config_content

            # Verify the config is set up correctly using git command
            repo = git.Repo(git_dir)
            assert repo.git.config("user.name") == "Directive User"
            assert repo.git.config("user.email") == "directive@example.com"

            # Run aider and verify it doesn't change the git config
            main(["--yes-always", "--exit"], **dummy_io)

            # Check that the git config file wasn't modified
            config_after_aider = git_config.read_text()
            assert modified_config_content == config_after_aider

            # Check that the user settings are still the same using git command
            repo = git.Repo(git_dir)  # Re-open repo to ensure we get fresh config
            assert repo.git.config("user.name") == "Directive User"
            assert repo.git.config("user.email") == "directive@example.com"

    def test_resolve_aiderignore_path(self, dummy_io):
        # Import the function directly to test it
        from aider.args import resolve_aiderignore_path

        # Test with absolute path
        abs_path = os.path.abspath("/tmp/test/.aiderignore")
        assert resolve_aiderignore_path(abs_path) == abs_path

        # Test with relative path and git root
        git_root = "/path/to/git/root"
        rel_path = ".aiderignore"
        assert resolve_aiderignore_path(rel_path, git_root) == str(Path(git_root) / rel_path)

        # Test with relative path and no git root
        rel_path = ".aiderignore"
        assert resolve_aiderignore_path(rel_path) == rel_path

    def test_invalid_edit_format(self, dummy_io):
        with GitTemporaryDirectory():
            # Suppress stderr for this test as argparse prints an error message
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as cm:
                    _ = main(
                        ["--edit-format", "not-a-real-format", "--exit", "--yes-always"],
                        **dummy_io,
                    )
                # argparse.ArgumentParser.exit() is called with status 2 for invalid choice
                assert cm.value.code == 2
                stderr_output = mock_stderr.getvalue()
                assert "invalid choice" in stderr_output
                assert "not-a-real-format" in stderr_output

    @pytest.mark.parametrize(
        "api_key_env,expected_model_substr",
        [
            ("ANTHROPIC_API_KEY", "sonnet"),
            ("DEEPSEEK_API_KEY", "deepseek"),
            ("OPENROUTER_API_KEY", "openrouter/"),
            ("OPENAI_API_KEY", "gpt-4"),
            ("GEMINI_API_KEY", "gemini"),
        ],
        ids=["anthropic", "deepseek", "openrouter", "openai", "gemini"],
    )
    def test_default_model_selection(self, api_key_env, expected_model_substr, dummy_io):
        with GitTemporaryDirectory():
            # Save and clear all API keys to test each one in isolation
            saved_keys = {}
            api_keys = [
                "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENROUTER_API_KEY",
                "OPENAI_API_KEY",
                "GEMINI_API_KEY",
            ]
            for key in api_keys:
                if key in os.environ:
                    saved_keys[key] = os.environ[key]
                    del os.environ[key]

            try:
                os.environ[api_key_env] = "test-key"
                coder = main(
                    ["--exit", "--yes-always"],
                    **dummy_io,
                    return_coder=True,
                )
                assert expected_model_substr in coder.main_model.name.lower()
            finally:
                # Restore saved API keys
                if api_key_env in os.environ:
                    del os.environ[api_key_env]
                for key, value in saved_keys.items():
                    os.environ[key] = value

    def test_default_model_selection_oauth_fallback(self, dummy_io):
        # Test no API keys - should offer OpenRouter OAuth
        with GitTemporaryDirectory():
            # Clear all API keys to simulate no configured keys
            saved_keys = {}
            api_keys = [
                "ANTHROPIC_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENROUTER_API_KEY",
                "OPENAI_API_KEY",
                "GEMINI_API_KEY",
            ]
            for key in api_keys:
                if key in os.environ:
                    saved_keys[key] = os.environ[key]
                    del os.environ[key]

            try:
                with patch("aider.onboarding.offer_openrouter_oauth") as mock_offer_oauth:
                    mock_offer_oauth.return_value = None  # Simulate user declining or failure
                    result = main(["--exit", "--yes-always"], **dummy_io)
                    assert result == 1  # Expect failure since no model could be selected
                    mock_offer_oauth.assert_called_once()
            finally:
                # Restore saved API keys
                for key, value in saved_keys.items():
                    os.environ[key] = value

    def test_model_precedence(self, dummy_io):
        with GitTemporaryDirectory():
            # Test that earlier API keys take precedence
            os.environ["ANTHROPIC_API_KEY"] = "test-key"
            os.environ["OPENAI_API_KEY"] = "test-key"
            coder = main(
                ["--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )
            assert "sonnet" in coder.main_model.name.lower()
            del os.environ["ANTHROPIC_API_KEY"]
            del os.environ["OPENAI_API_KEY"]

    def test_model_overrides_suffix_applied(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)
            overrides_file = git_dir / ".aider.model.overrides.yml"
            overrides_file.write_text("gpt-4o:\n  fast:\n    temperature: 0.1\n")

            with (
                patch("aider.models.Model") as MockModel,
                patch("aider.coders.Coder.create") as MockCoder,
            ):
                mock_coder_instance = MagicMock()
                mock_coder_instance._autosave_future = mock_autosave_future()
                MockCoder.return_value = mock_coder_instance

                mock_instance = MockModel.return_value
                mock_instance.info = {}
                mock_instance.name = "gpt-4o"
                mock_instance.validate_environment.return_value = {
                    "missing_keys": [],
                    "keys_in_environment": [],
                }
                mock_instance.accepts_settings = []
                mock_instance.weak_model_name = None
                mock_instance.get_weak_model.return_value = None

                main(
                    ["--model", "gpt-4o:fast", "--exit", "--yes-always", "--no-git"],
                    **dummy_io,
                    force_git_root=git_dir,
                )

                # Find the call that constructed the main model with overrides
                matched_call_found = False
                for call_args in MockModel.call_args_list:
                    args, kwargs = call_args
                    if (
                        args
                        and args[0] == "gpt-4o"
                        and kwargs.get("override_kwargs") == {"temperature": 0.1}
                    ):
                        matched_call_found = True
                        break

                assert matched_call_found, (
                    "Expected a Model call with base name 'gpt-4o' and override_kwargs"
                    " {'temperature': 0.1}"
                )

    def test_model_overrides_no_match_preserves_model_name(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)

            with (
                patch("aider.models.Model") as MockModel,
                patch("aider.coders.Coder.create") as MockCoder,
            ):
                mock_coder_instance = MagicMock()
                mock_coder_instance._autosave_future = mock_autosave_future()
                MockCoder.return_value = mock_coder_instance

                mock_instance = MockModel.return_value
                mock_instance.info = {}
                mock_instance.name = "test-model"
                mock_instance.validate_environment.return_value = {
                    "missing_keys": [],
                    "keys_in_environment": [],
                }
                mock_instance.accepts_settings = []
                mock_instance.weak_model_name = None
                mock_instance.get_weak_model.return_value = None

                model_name = "hf:moonshotai/Kimi-K2-Thinking"

                main(
                    ["--model", model_name, "--exit", "--yes-always", "--no-git"],
                    **dummy_io,
                    force_git_root=git_dir,
                )

                matched_call_found = False
                for call_args in MockModel.call_args_list:
                    args, kwargs = call_args
                    if args and args[0] == model_name and kwargs.get("override_kwargs") == {}:
                        matched_call_found = True
                        break

                assert matched_call_found, (
                    "Expected a Model call with the full model name preserved and empty"
                    " override_kwargs"
                )

    def test_chat_language_spanish(self, dummy_io):
        with GitTemporaryDirectory():
            coder = main(
                ["--chat-language", "Spanish", "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )
            system_info = coder.get_platform_info()
            assert "Spanish" in system_info

    def test_commit_language_japanese(self, dummy_io):
        with GitTemporaryDirectory():
            coder = main(
                ["--commit-language", "japanese", "--exit", "--yes-always"],
                **dummy_io,
                return_coder=True,
            )
            assert "japanese" in coder.commit_language

    @patch("git.Repo.init")
    def test_main_exit_with_git_command_not_found(self, mock_git_init, dummy_io):
        mock_git_init.side_effect = git.exc.GitCommandNotFound("git", "Command 'git' not found")

        result = main(["--exit", "--yes-always"], **dummy_io)
        assert result == 0, "main() should return 0 (success) when called with --exit"

    def test_reasoning_effort_option(self, dummy_io):
        coder = main(
            [
                "--reasoning-effort",
                "3",
                "--no-check-model-accepts-settings",
                "--yes-always",
                "--exit",
            ],
            **dummy_io,
            return_coder=True,
        )
        assert coder.main_model.extra_params.get("extra_body", {}).get("reasoning_effort") == "3"

    def test_thinking_tokens_option(self, dummy_io):
        coder = main(
            ["--model", "sonnet", "--thinking-tokens", "1000", "--yes-always", "--exit"],
            **dummy_io,
            return_coder=True,
        )
        assert coder.main_model.extra_params.get("thinking", {}).get("budget_tokens") == 1000

    def test_list_models_includes_metadata_models(self, dummy_io):
        # Test that models from model-metadata.json appear in list-models output
        with GitTemporaryDirectory():
            # Create a temporary model-metadata.json with test models
            metadata_file = Path(".aider.model.metadata.json")
            test_models = {
                "unique-model-name": {
                    "max_input_tokens": 8192,
                    "litellm_provider": "test-provider",
                    "mode": "chat",  # Added mode attribute
                },
                "another-provider/another-unique-model": {
                    "max_input_tokens": 4096,
                    "litellm_provider": "another-provider",
                    "mode": "chat",  # Added mode attribute
                },
            }
            metadata_file.write_text(json.dumps(test_models))

            # Capture stdout to check the output
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main(
                    [
                        "--list-models",
                        "unique-model",
                        "--model-metadata-file",
                        str(metadata_file),
                        "--yes-always",
                        "--no-gitignore",
                    ],
                    **dummy_io,
                )
                output = mock_stdout.getvalue()

                # Check that the unique model name from our metadata file is listed
                assert "test-provider/unique-model-name" in output

    def test_list_models_includes_all_model_sources(self, dummy_io):
        # Test that models from both litellm.model_cost and model-metadata.json
        # appear in list-models
        with GitTemporaryDirectory():
            # Create a temporary model-metadata.json with test models
            metadata_file = Path(".aider.model.metadata.json")
            test_models = {
                "metadata-only-model": {
                    "max_input_tokens": 8192,
                    "litellm_provider": "test-provider",
                    "mode": "chat",  # Added mode attribute
                }
            }
            metadata_file.write_text(json.dumps(test_models))

            # Capture stdout to check the output
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main(
                    [
                        "--list-models",
                        "metadata-only-model",
                        "--model-metadata-file",
                        str(metadata_file),
                        "--yes-always",
                        "--no-gitignore",
                    ],
                    **dummy_io,
                )
                output = mock_stdout.getvalue()

                dump(output)

                # Check that both models appear in the output
                assert "test-provider/metadata-only-model" in output

    def test_check_model_accepts_settings_flag(self, dummy_io):
        # Test that --check-model-accepts-settings affects whether settings are applied
        with GitTemporaryDirectory():
            # When flag is on, setting shouldn't be applied to non-supporting model
            with patch("aider.models.Model.set_thinking_tokens") as mock_set_thinking:
                main(
                    [
                        "--model",
                        "gpt-4o",
                        "--thinking-tokens",
                        "1000",
                        "--check-model-accepts-settings",
                        "--yes-always",
                        "--exit",
                    ],
                    **dummy_io,
                )
                # Method should not be called because model doesn't support it and flag is on
                mock_set_thinking.assert_not_called()

    def test_list_models_with_direct_resource_patch(self, dummy_io):
        # Test that models from resources/model-metadata.json are included in list-models output
        with GitTemporaryDirectory():
            # Create a temporary file with test model metadata
            test_file = Path(self.tempdir) / "test-model-metadata.json"
            test_resource_models = {
                "special-model": {
                    "max_input_tokens": 8192,
                    "litellm_provider": "resource-provider",
                    "mode": "chat",
                }
            }
            test_file.write_text(json.dumps(test_resource_models))

            # Create a mock for the resource file path
            mock_resource_path = MagicMock()
            mock_resource_path.__str__.return_value = str(test_file)

            # Create a mock for the files function that returns an object with joinpath
            mock_files = MagicMock()
            mock_files.joinpath.return_value = mock_resource_path

            with patch("aider.main.importlib_resources.files", return_value=mock_files):
                # Capture stdout to check the output
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    main(
                        ["--list-models", "special", "--yes-always", "--no-gitignore"],
                        **dummy_io,
                    )
                    output = mock_stdout.getvalue()

                    # Check that the resource model appears in the output
                    assert "resource-provider/special-model" in output

            # When flag is off, setting should be applied regardless of support
            with patch("aider.models.Model.set_reasoning_effort") as mock_set_reasoning:
                main(
                    [
                        "--model",
                        "gpt-3.5-turbo",
                        "--reasoning-effort",
                        "3",
                        "--no-check-model-accepts-settings",
                        "--yes-always",
                        "--exit",
                    ],
                    **dummy_io,
                )
                # Method should be called because flag is off
                mock_set_reasoning.assert_called_once_with("3")

    def test_model_accepts_settings_attribute(self, dummy_io):
        with GitTemporaryDirectory():
            # Test with a model where we override the accepts_settings attribute
            with patch("aider.models.Model") as MockModel:
                # Setup mock model instance to simulate accepts_settings attribute
                mock_instance = MockModel.return_value
                mock_instance.name = "test-model"
                mock_instance.accepts_settings = ["reasoning_effort"]
                mock_instance.validate_environment.return_value = {
                    "missing_keys": [],
                    "keys_in_environment": [],
                }
                mock_instance.info = {}
                mock_instance.weak_model_name = None
                mock_instance.get_weak_model.return_value = None

                # Run with both settings, but model only accepts reasoning_effort
                main(
                    [
                        "--model",
                        "test-model",
                        "--reasoning-effort",
                        "3",
                        "--thinking-tokens",
                        "1000",
                        "--check-model-accepts-settings",
                        "--yes-always",
                        "--exit",
                    ],
                    **dummy_io,
                )

                # Only set_reasoning_effort should be called, not set_thinking_tokens
                mock_instance.set_reasoning_effort.assert_called_once_with("3")
                mock_instance.set_thinking_tokens.assert_not_called()

    @patch("aider.main.InputOutput", autospec=True)
    def test_stream_and_cache_warning(self, MockInputOutput, dummy_io):
        mock_io_instance = MockInputOutput.return_value
        mock_io_instance.pretty = True
        with GitTemporaryDirectory():
            main(
                ["--stream", "--cache-prompts", "--exit", "--yes-always"],
                **dummy_io,
            )
        mock_io_instance.tool_warning.assert_called_with(
            "Cost estimates may be inaccurate when using streaming and caching."
        )

    @patch("aider.main.InputOutput", autospec=True)
    def test_stream_without_cache_no_warning(self, MockInputOutput, dummy_io):
        mock_io_instance = MockInputOutput.return_value
        mock_io_instance.pretty = True
        with GitTemporaryDirectory():
            main(
                ["--stream", "--exit", "--yes-always"],
                **dummy_io,
            )
        for call in mock_io_instance.tool_warning.call_args_list:
            assert "Cost estimates may be inaccurate" not in call[0][0]

    def test_argv_file_respects_git(self, dummy_io):
        with GitTemporaryDirectory():
            fname = Path("not_in_git.txt")
            fname.touch()
            with open(".gitignore", "w+") as f:
                f.write("not_in_git.txt")
            coder = main(
                argv=["--file", "not_in_git.txt"],
                **dummy_io,
                return_coder=True,
            )
            assert "not_in_git.txt" not in str(coder.abs_fnames)
            assert not asyncio.run(coder.allowed_to_edit("not_in_git.txt"))

    def test_load_dotenv_files_override(self, dummy_io):
        with GitTemporaryDirectory() as git_dir:
            git_dir = Path(git_dir)

            # Create fake home and .aider directory
            fake_home = git_dir / "fake_home"
            fake_home.mkdir()
            aider_dir = fake_home / ".aider"
            aider_dir.mkdir()

            # Create oauth keys file
            oauth_keys_file = aider_dir / "oauth-keys.env"
            oauth_keys_file.write_text("OAUTH_VAR=oauth_val\nSHARED_VAR=oauth_shared\n")

            # Create git root .env file
            git_root_env = git_dir / ".env"
            git_root_env.write_text("GIT_VAR=git_val\nSHARED_VAR=git_shared\n")

            # Create CWD .env file in a subdir
            cwd_subdir = git_dir / "subdir"
            cwd_subdir.mkdir()
            cwd_env = cwd_subdir / ".env"
            cwd_env.write_text("CWD_VAR=cwd_val\nSHARED_VAR=cwd_shared\n")

            # Change to subdir
            original_cwd = os.getcwd()
            os.chdir(cwd_subdir)

            # Clear relevant env vars before test
            for var in ["OAUTH_VAR", "SHARED_VAR", "GIT_VAR", "CWD_VAR"]:
                if var in os.environ:
                    del os.environ[var]

            with patch("pathlib.Path.home", return_value=fake_home):
                loaded_files = load_dotenv_files(str(git_dir), None)

                # Assert files were loaded in expected order (oauth first)
                assert str(oauth_keys_file.resolve()) in loaded_files
                assert str(git_root_env.resolve()) in loaded_files
                assert str(cwd_env.resolve()) in loaded_files
                assert loaded_files.index(str(oauth_keys_file.resolve())) < loaded_files.index(
                    str(git_root_env.resolve())
                )
                assert loaded_files.index(str(git_root_env.resolve())) < loaded_files.index(
                    str(cwd_env.resolve())
                )

                # Assert environment variables reflect the override order
                assert os.environ.get("OAUTH_VAR") == "oauth_val"
                assert os.environ.get("GIT_VAR") == "git_val"
                assert os.environ.get("CWD_VAR") == "cwd_val"
                # SHARED_VAR should be overridden by the last loaded file (cwd .env)
                assert os.environ.get("SHARED_VAR") == "cwd_shared"

            # Restore CWD
            os.chdir(original_cwd)

    @patch("aider.main.InputOutput", autospec=True)
    def test_cache_without_stream_no_warning(self, MockInputOutput, dummy_io):
        mock_io_instance = MockInputOutput.return_value
        mock_io_instance.pretty = True
        with GitTemporaryDirectory():
            main(
                ["--cache-prompts", "--exit", "--yes-always", "--no-stream"],
                **dummy_io,
            )
        for call in mock_io_instance.tool_warning.call_args_list:
            assert "Cost estimates may be inaccurate" not in call[0][0]

    @patch("aider.coders.Coder.create")
    def test_mcp_servers_parsing(self, mock_coder_create, dummy_io):
        # Setup mock coder
        mock_coder_instance = MagicMock()
        mock_coder_instance._autosave_future = mock_autosave_future()
        mock_coder_create.return_value = mock_coder_instance

        # Test with --mcp-servers option
        with GitTemporaryDirectory():
            main(
                [
                    "--mcp-servers",
                    '{"mcpServers":{"git":{"command":"uvx","args":["mcp-server-git"]}}}',
                    "--exit",
                    "--yes-always",
                ],
                **dummy_io,
            )

            # Verify that Coder.create was called with mcp_servers parameter
            mock_coder_create.assert_called_once()
            _, kwargs = mock_coder_create.call_args
            assert "mcp_servers" in kwargs
            assert kwargs["mcp_servers"] is not None
            # At least one server should be in the list
            assert len(kwargs["mcp_servers"]) > 0
            # First server should have a name attribute
            assert hasattr(kwargs["mcp_servers"][0], "name")

        # Test with --mcp-servers-file option
        mock_coder_create.reset_mock()
        mock_coder_instance._autosave_future = mock_autosave_future()

        with GitTemporaryDirectory():
            # Create a temporary MCP servers file
            mcp_file = Path("mcp_servers.json")
            mcp_content = {"mcpServers": {"git": {"command": "uvx", "args": ["mcp-server-git"]}}}
            mcp_file.write_text(json.dumps(mcp_content))

            main(
                ["--mcp-servers-file", str(mcp_file), "--exit", "--yes-always"],
                **dummy_io,
            )

            # Verify that Coder.create was called with mcp_servers parameter
            mock_coder_create.assert_called_once()
            _, kwargs = mock_coder_create.call_args
            assert "mcp_servers" in kwargs
            assert kwargs["mcp_servers"] is not None
            # At least one server should be in the list
            assert len(kwargs["mcp_servers"]) > 0
            # First server should have a name attribute
            assert hasattr(kwargs["mcp_servers"][0], "name")
