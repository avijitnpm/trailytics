"""Unit tests for Trailytics CLI, repository discovery, and subprocess runner."""

import os
from pathlib import Path
import subprocess
from unittest import mock
import urllib.error
import pytest
from click.testing import CliRunner

import trailytics
from trailytics.cli.main import cli
from trailytics.cli.runner import (
    execute_lifecycle_script,
    find_repository_root,
    get_repository_metadata,
    get_repository_root,
    is_valid_repository_root,
    run_script,
)
from trailytics.exceptions import RepositoryNotFoundError, ScriptExecutionError


@pytest.fixture
def cli_runner():
    """Click CLI test runner fixture."""
    return CliRunner()


@pytest.fixture
def mock_repo_dir(tmp_path):
    """Create a temporary mock Trailytics repository with all required markers."""
    repo = tmp_path / "mock_trailytics_repo"
    repo.mkdir()
    (repo / "trailytics").mkdir()
    for s in ["start.sh", "stop.sh", "status.sh", "lib.sh", "build-frontend.sh", "install.sh", "logs.sh", "doctor.sh"]:
        f = repo / "trailytics" / s
        f.write_text("#!/bin/bash\n")
        f.chmod(0o755)
    (repo / "config").mkdir()
    (repo / "config" / "trailytics.env").write_text(
        "OPIK_VERSION=2.2.138\n"
        "OPIK_COMMIT=28192d8ffe85299f5c44032f705a9e518e6d1189\n"
        "TRAILYTICS_COMPOSE_PROJECT=opik-opik\n"
        "TRAILYTICS_DASHBOARD_PORT=5173\n"
    )
    (repo / "upstream" / "opik" / ".git").mkdir(parents=True)
    (repo / "upstream" / "opik" / "deployment" / "docker-compose").mkdir(parents=True)
    (repo / "upstream" / "opik" / "deployment" / "docker-compose" / "docker-compose.yaml").write_text("name: opik\n")
    (repo / "pyproject.toml").write_text("[project]\nname='trailytics'\n")
    return repo


# ============================================================================
# 1. CLI Tests
# ============================================================================


def test_cli_help(cli_runner):
    """Verify 'trailytics --help' displays usage, options, and registered commands."""
    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Trailytics - AI Observability & Tracing CLI." in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "restart" in result.output
    assert "status" in result.output
    assert "logs" in result.output
    assert "doctor" in result.output
    assert "version" in result.output
    assert "--help" in result.output
    assert "--version" in result.output


def test_cli_version_flag(cli_runner):
    """Verify 'trailytics --version' displays the package version."""
    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert f"trailytics {trailytics.__version__}" in result.output


def test_cli_version_command_with_repo(cli_runner):
    """Verify 'trailytics version' displays structured version metadata."""
    result = cli_runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().split("\n")]
    assert any("Trailytics" in line and "0.3.0" in line for line in lines)
    assert any("Opik Engine" in line and "2.2.138" in line for line in lines)
    assert any("Commit" in line and "28192d8ffe85299f5c44032f705a9e518e6d1189" in line for line in lines)


def test_cli_version_command_fallback_when_repo_not_found(cli_runner):
    """Verify 'trailytics version' falls back gracefully when repository cannot be located."""
    with mock.patch("trailytics.cli.commands.version.find_repository_root", return_value=None):
        result = cli_runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "Trailytics" in result.output
        assert "0.3.0" in result.output
        assert "unavailable (repository not located)" in result.output


def test_cli_invalid_command(cli_runner):
    """Verify invalid CLI command returns non-zero exit code and helpful message."""
    result = cli_runner.invoke(cli, ["unknown-cmd"])
    assert result.exit_code == 2
    assert "No such command" in result.output


# ============================================================================
# 2. Repository Discovery Tests
# ============================================================================


def test_is_valid_repository_root(mock_repo_dir, tmp_path):
    """Verify repository root validation logic."""
    assert is_valid_repository_root(mock_repo_dir) is True

    # Missing markers
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    assert is_valid_repository_root(empty_dir) is False

    # Missing config/trailytics.env
    broken_repo = tmp_path / "broken_repo"
    broken_repo.mkdir()
    (broken_repo / "trailytics").mkdir()
    (broken_repo / "upstream" / "opik").mkdir(parents=True)
    (broken_repo / "pyproject.toml").touch()
    assert is_valid_repository_root(broken_repo) is False


def test_find_repo_via_explicit_env(mock_repo_dir):
    """Verify TRAILYTICS_REPO_DIR is respected when valid."""
    with mock.patch.dict(os.environ, {"TRAILYTICS_REPO_DIR": str(mock_repo_dir)}):
        discovered = find_repository_root()
        assert discovered == mock_repo_dir.resolve()


def test_find_repo_via_explicit_invalid_env(tmp_path):
    """Verify invalid TRAILYTICS_REPO_DIR raises RepositoryNotFoundError without falling back."""
    invalid_path = tmp_path / "nonexistent_repo"
    invalid_path.mkdir()
    with mock.patch.dict(os.environ, {"TRAILYTICS_REPO_DIR": str(invalid_path)}):
        with pytest.raises(RepositoryNotFoundError) as exc_info:
            find_repository_root()
        assert "is not a valid Trailytics repository" in str(exc_info.value)


def test_find_repo_via_cwd(mock_repo_dir):
    """Verify repository is discovered when current working directory is the repo root."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("pathlib.Path.cwd", return_value=mock_repo_dir):
            discovered = find_repository_root()
            assert discovered == mock_repo_dir.resolve()


def test_find_repo_via_parent_of_cwd(mock_repo_dir):
    """Verify repository is discovered when cwd is a subdirectory of the repo."""
    sub_dir = mock_repo_dir / "src" / "deep" / "nested"
    sub_dir.mkdir(parents=True)
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("pathlib.Path.cwd", return_value=sub_dir):
            discovered = find_repository_root()
            assert discovered == mock_repo_dir.resolve()


def test_find_repo_via_module_location():
    """Verify repository is discovered from the actual module location in the repository."""
    with mock.patch.dict(os.environ, {}, clear=True):
        # Force cwd to /tmp where no markers exist
        with mock.patch("pathlib.Path.cwd", return_value=Path("/tmp")):
            discovered = find_repository_root()
            assert discovered is not None
            assert is_valid_repository_root(discovered) is True


def test_get_repository_root_not_found():
    """Verify get_repository_root raises RepositoryNotFoundError when no repo is found."""
    with mock.patch("trailytics.cli.runner.find_repository_root", return_value=None):
        with pytest.raises(RepositoryNotFoundError) as exc_info:
            get_repository_root()
        assert "Trailytics repository could not be located" in str(exc_info.value)


def test_repo_path_with_spaces(tmp_path):
    """Verify repository discovery works when the path contains spaces."""
    repo_with_spaces = tmp_path / "My Special Projects" / "trailytics repo"
    repo_with_spaces.mkdir(parents=True)
    (repo_with_spaces / "trailytics").mkdir()
    (repo_with_spaces / "config").mkdir()
    (repo_with_spaces / "config" / "trailytics.env").write_text("OPIK_VERSION=2.2.138\n")
    (repo_with_spaces / "upstream" / "opik").mkdir(parents=True)
    (repo_with_spaces / "pyproject.toml").write_text("[project]\nname='trailytics'\n")

    assert is_valid_repository_root(repo_with_spaces) is True
    with mock.patch.dict(os.environ, {"TRAILYTICS_REPO_DIR": str(repo_with_spaces)}):
        assert find_repository_root() == repo_with_spaces.resolve()


def test_get_repository_metadata(mock_repo_dir):
    """Verify metadata extraction from config/trailytics.env."""
    meta = get_repository_metadata(mock_repo_dir)
    assert meta.get("OPIK_VERSION") == "2.2.138"
    assert meta.get("OPIK_COMMIT") == "28192d8ffe85299f5c44032f705a9e518e6d1189"
    assert meta.get("TRAILYTICS_COMPOSE_PROJECT") == "opik-opik"


# ============================================================================
# 3. Subprocess Runner Tests
# ============================================================================


def test_run_script_success(mock_repo_dir):
    """Verify run_script executes the specified script in the repo root directory."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "start.sh")],
                returncode=0,
                stdout="Started",
                stderr="",
            )

            res = run_script("start.sh", args=["--flag", "val"], env={"CUSTOM_VAR": "1"})

            assert res.returncode == 0
            mock_run.assert_called_once()
            called_args, called_kwargs = mock_run.call_args

            # Check command
            expected_cmd = ["bash", str(mock_repo_dir / "trailytics" / "start.sh"), "--flag", "val"]
            assert called_args[0] == expected_cmd

            # Check working directory is repo root
            assert called_kwargs["cwd"] == str(mock_repo_dir)

            # Check environment preservation + override
            assert called_kwargs["env"]["CUSTOM_VAR"] == "1"
            assert "PATH" in called_kwargs["env"]

            # Check shell=False
            assert called_kwargs.get("shell", False) is False


def test_run_script_missing_script(mock_repo_dir):
    """Verify run_script raises FileNotFoundError if script does not exist."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with pytest.raises(FileNotFoundError) as exc_info:
            run_script("nonexistent_script.sh")
        assert "Trailytics script not found" in str(exc_info.value)


def test_run_script_failure_propagation(mock_repo_dir):
    """Verify run_script raises ScriptExecutionError when check=True and script exits non-zero."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "start.sh")],
                returncode=1,
                stdout="",
                stderr="Container failure",
            )

            with pytest.raises(ScriptExecutionError) as exc_info:
                run_script("start.sh", capture_output=True, check=True)

            assert exc_info.value.exit_code == 1
            assert "exited with status 1" in str(exc_info.value)
            assert "Container failure" in str(exc_info.value)


def test_run_script_without_check_returns_failed_process(mock_repo_dir):
    """Verify run_script returns CompletedProcess without raising when check=False."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "start.sh")],
                returncode=42,
            )

            result = run_script("start.sh", check=False)
            assert result.returncode == 42


# ============================================================================
# 4. Lifecycle Command Tests
# ============================================================================


def test_start_command_success(cli_runner, mock_repo_dir):
    """Verify 'trailytics start' invokes start.sh with repository root cwd."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "start.sh")],
                returncode=0,
            )

            result = cli_runner.invoke(cli, ["start"])
            assert result.exit_code == 0
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "start.sh")]
            assert kwargs["cwd"] == str(mock_repo_dir)
            assert kwargs["capture_output"] is False
            assert kwargs.get("shell", False) is False


def test_start_command_failure_propagation(cli_runner, mock_repo_dir):
    """Verify 'trailytics start' propagates nonzero exit codes from start.sh."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "start.sh")],
                returncode=1,
            )

            result = cli_runner.invoke(cli, ["start"])
            assert result.exit_code == 1


def test_start_command_custom_exit_code_propagation(cli_runner, mock_repo_dir):
    """Verify 'trailytics start' preserves specific nonzero exit codes."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "start.sh")],
                returncode=42,
            )

            result = cli_runner.invoke(cli, ["start"])
            assert result.exit_code == 42


def test_start_command_repo_not_found(cli_runner):
    """Verify 'trailytics start' outputs clear error and exits 1 when repository not found or standalone fails."""
    with mock.patch("trailytics.cli.runner.find_repository_root", return_value=None):
        result = cli_runner.invoke(cli, ["start"])
        assert result.exit_code == 1
        assert "Trailytics Error" in result.output
        assert ("repository could not be located" in result.output) or ("Docker" in result.output)


def test_start_command_missing_script(cli_runner, mock_repo_dir):
    """Verify 'trailytics start' outputs clear error when start.sh is missing."""
    (mock_repo_dir / "trailytics" / "start.sh").unlink()
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        result = cli_runner.invoke(cli, ["start"])
        assert result.exit_code == 1
        assert "Trailytics Error" in result.output
        assert "script not found" in result.output


def test_stop_command_success(cli_runner, mock_repo_dir):
    """Verify 'trailytics stop' invokes stop.sh with repository root cwd."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "stop.sh")],
                returncode=0,
            )

            result = cli_runner.invoke(cli, ["stop"])
            assert result.exit_code == 0
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "stop.sh")]
            assert kwargs["cwd"] == str(mock_repo_dir)
            assert kwargs["capture_output"] is False
            assert kwargs.get("shell", False) is False


def test_stop_command_failure_propagation(cli_runner, mock_repo_dir):
    """Verify 'trailytics stop' propagates nonzero exit codes from stop.sh."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "stop.sh")],
                returncode=1,
            )

            result = cli_runner.invoke(cli, ["stop"])
            assert result.exit_code == 1


def test_stop_command_repo_not_found(cli_runner):
    """Verify 'trailytics stop' outputs clear error when repository not found or standalone fails."""
    with mock.patch("trailytics.cli.runner.find_repository_root", return_value=None):
        result = cli_runner.invoke(cli, ["stop"])
        assert result.exit_code == 1
        assert "Trailytics Error" in result.output
        assert ("repository could not be located" in result.output) or ("Docker" in result.output)


def test_restart_command_success(cli_runner):
    """Verify 'trailytics restart' executes stop then start on success."""
    with mock.patch("trailytics.cli.commands.restart.run_stop", return_value=0) as mock_stop, \
         mock.patch("trailytics.cli.commands.restart.run_start", return_value=0) as mock_start:

        result = cli_runner.invoke(cli, ["restart"])
        assert result.exit_code == 0
        mock_stop.assert_called_once()
        mock_start.assert_called_once()


def test_restart_command_stop_failure_aborts_before_start(cli_runner):
    """Verify 'trailytics restart' aborts immediately if stop fails without calling start."""
    with mock.patch("trailytics.cli.commands.restart.run_stop", return_value=2) as mock_stop, \
         mock.patch("trailytics.cli.commands.restart.run_start") as mock_start:

        result = cli_runner.invoke(cli, ["restart"])
        assert result.exit_code == 2
        mock_stop.assert_called_once()
        mock_start.assert_not_called()
        assert "stopping deployment failed; aborting restart" in result.output


def test_restart_command_start_failure_propagates(cli_runner):
    """Verify 'trailytics restart' calls start after successful stop and propagates start failure."""
    with mock.patch("trailytics.cli.commands.restart.run_stop", return_value=0) as mock_stop, \
         mock.patch("trailytics.cli.commands.restart.run_start", return_value=5) as mock_start:

        result = cli_runner.invoke(cli, ["restart"])
        assert result.exit_code == 5
        mock_stop.assert_called_once()
        mock_start.assert_called_once()


def test_status_command_success(cli_runner, mock_repo_dir):
    """Verify 'trailytics status' invokes status.sh with repository root cwd."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "status.sh")],
                returncode=0,
            )

            result = cli_runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "status.sh")]
            assert kwargs["cwd"] == str(mock_repo_dir)
            assert kwargs["capture_output"] is False


def test_status_command_is_read_only(cli_runner):
    """Verify 'trailytics status' only executes status.sh and never invokes start or stop."""
    with mock.patch("trailytics.cli.runner.run_script") as mock_run_script:
        mock_run_script.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        result = cli_runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        mock_run_script.assert_called_once_with(
            "status.sh",
            args=None,
            env=None,
            capture_output=False,
            check=False,
        )


def test_status_command_failure_propagation(cli_runner, mock_repo_dir):
    """Verify 'trailytics status' propagates nonzero exit codes from status.sh."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", str(mock_repo_dir / "trailytics" / "status.sh")],
                returncode=1,
            )

            result = cli_runner.invoke(cli, ["status"])
            assert result.exit_code == 1


def test_execute_lifecycle_script_handles_script_execution_error():
    """Verify execute_lifecycle_script handles ScriptExecutionError gracefully."""
    with mock.patch("trailytics.cli.runner.run_script", side_effect=ScriptExecutionError("Execution failed", exit_code=3)):
        code = execute_lifecycle_script("some_script.sh")
        assert code == 3


def test_execute_lifecycle_script_handles_os_error():
    """Verify execute_lifecycle_script handles OSError gracefully."""
    with mock.patch("trailytics.cli.runner.run_script", side_effect=OSError("Exec format error")):
        code = execute_lifecycle_script("some_script.sh")
        assert code == 1


def test_execute_lifecycle_script_keyboard_interrupt_default_returns_130():
    """Verify KeyboardInterrupt returns exit code 130 and error message when allow_interrupt=False."""
    with mock.patch("trailytics.cli.runner.run_script", side_effect=KeyboardInterrupt()):
        code = execute_lifecycle_script("start.sh", allow_interrupt=False)
        assert code == 130


def test_execute_lifecycle_script_keyboard_interrupt_when_allowed_returns_0():
    """Verify KeyboardInterrupt returns exit code 0 cleanly when allow_interrupt=True."""
    with mock.patch("trailytics.cli.runner.run_script", side_effect=KeyboardInterrupt()):
        code = execute_lifecycle_script("logs.sh", allow_interrupt=True)
        assert code == 0


def test_start_command_interrupted_by_user_fails_with_code_130(cli_runner, mock_repo_dir):
    """Verify interrupting 'trailytics start' exits with code 130 rather than success."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir), \
         mock.patch("trailytics.cli.runner.run_script", side_effect=KeyboardInterrupt()):

        result = cli_runner.invoke(cli, ["start"])
        assert result.exit_code == 130
        assert "interrupted by user" in result.output


def test_stop_command_interrupted_by_user_fails_with_code_130(cli_runner, mock_repo_dir):
    """Verify interrupting 'trailytics stop' exits with code 130 rather than success."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir), \
         mock.patch("trailytics.cli.runner.run_script", side_effect=KeyboardInterrupt()):

        result = cli_runner.invoke(cli, ["stop"])
        assert result.exit_code == 130
        assert "interrupted by user" in result.output


def test_restart_command_interrupted_during_stop_aborts_without_starting(cli_runner):
    """Verify interrupting stop during 'trailytics restart' aborts before starting."""
    with mock.patch("trailytics.cli.commands.restart.run_stop", return_value=130) as mock_stop, \
         mock.patch("trailytics.cli.commands.restart.run_start") as mock_start:

        result = cli_runner.invoke(cli, ["restart"])
        assert result.exit_code == 130
        mock_stop.assert_called_once()
        mock_start.assert_not_called()
        assert "stopping deployment failed; aborting restart" in result.output


def test_logs_command_interrupted_by_user_exits_cleanly_code_0(cli_runner, mock_repo_dir):
    """Verify interrupting 'trailytics logs -f' exits cleanly with code 0."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir), \
         mock.patch("trailytics.cli.runner.run_script", side_effect=KeyboardInterrupt()):

        result = cli_runner.invoke(cli, ["logs", "-f"])
        assert result.exit_code == 0



# ============================================================================
# 5. Logs Command Tests
# ============================================================================


def test_logs_command_help(cli_runner):
    """Verify 'trailytics logs --help' displays usage and options."""
    result = cli_runner.invoke(cli, ["logs", "--help"])
    assert result.exit_code == 0
    assert "View logs from deployment containers." in result.output
    assert "--follow" in result.output
    assert "--tail" in result.output
    assert "--since" in result.output
    assert "--timestamps" in result.output


def test_logs_command_default_tail(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs' invokes logs.sh with default --tail 100."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = cli_runner.invoke(cli, ["logs"])
            assert result.exit_code == 0
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "logs.sh"), "--tail", "100"]
            assert kwargs["cwd"] == str(mock_repo_dir)
            assert kwargs["capture_output"] is False
            assert kwargs.get("shell", False) is False


def test_logs_command_follow(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs -f' passes -f and --tail 100."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = cli_runner.invoke(cli, ["logs", "-f"])
            assert result.exit_code == 0
            args, _ = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "logs.sh"), "-f", "--tail", "100"]


def test_logs_command_custom_tail(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs --tail 250' passes custom tail value."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = cli_runner.invoke(cli, ["logs", "--tail", "250"])
            assert result.exit_code == 0
            args, _ = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "logs.sh"), "--tail", "250"]


def test_logs_command_tail_all(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs --tail all' allows 'all' as a valid tail parameter."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = cli_runner.invoke(cli, ["logs", "--tail", "all"])
            assert result.exit_code == 0
            args, _ = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "logs.sh"), "--tail", "all"]


def test_logs_command_invalid_tail(cli_runner):
    """Verify 'trailytics logs --tail invalid' rejects non-integer/non-all values."""
    result = cli_runner.invoke(cli, ["logs", "--tail", "invalid"])
    assert result.exit_code == 2
    assert "Invalid tail value" in result.output


def test_logs_command_since(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs --since 30m' passes duration to logs.sh."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = cli_runner.invoke(cli, ["logs", "--since", "30m"])
            assert result.exit_code == 0
            args, _ = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "logs.sh"), "--tail", "100", "--since", "30m"]


def test_logs_command_empty_since(cli_runner):
    """Verify 'trailytics logs --since \"\"' rejects empty duration."""
    result = cli_runner.invoke(cli, ["logs", "--since", ""])
    assert result.exit_code == 2
    assert "Duration cannot be empty" in result.output


def test_logs_command_timestamps(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs -t' passes --timestamps flag."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = cli_runner.invoke(cli, ["logs", "-t"])
            assert result.exit_code == 0
            args, _ = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "logs.sh"), "--tail", "100", "--timestamps"]


def test_logs_command_services_filter(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs backend frontend' filters to specific services."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

            result = cli_runner.invoke(cli, ["logs", "backend", "frontend"])
            assert result.exit_code == 0
            args, _ = mock_run.call_args
            assert args[0] == ["bash", str(mock_repo_dir / "trailytics" / "logs.sh"), "--tail", "100", "backend", "frontend"]


def test_logs_command_failure_propagation(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs' propagates nonzero exit codes."""
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1)

            result = cli_runner.invoke(cli, ["logs", "invalid-service"])
            assert result.exit_code == 1


def test_logs_command_repo_not_found(cli_runner):
    """Verify 'trailytics logs' outputs clear error when repository not found or standalone fails."""
    with mock.patch("trailytics.cli.runner.find_repository_root", return_value=None):
        result = cli_runner.invoke(cli, ["logs"])
        assert result.exit_code == 1
        assert "Trailytics Error" in result.output
        assert ("repository could not be located" in result.output) or ("Docker" in result.output)


def test_logs_command_missing_script(cli_runner, mock_repo_dir):
    """Verify 'trailytics logs' outputs clear error when logs.sh is missing."""
    (mock_repo_dir / "trailytics" / "logs.sh").unlink()
    with mock.patch("trailytics.cli.runner.get_repository_root", return_value=mock_repo_dir):
        result = cli_runner.invoke(cli, ["logs"])
        assert result.exit_code == 1
        assert "Trailytics Error" in result.output
        assert "script not found" in result.output


# ============================================================================
# 6. Doctor Command Tests
# ============================================================================


def test_doctor_command_help(cli_runner):
    """Verify 'trailytics doctor --help' displays usage and help."""
    result = cli_runner.invoke(cli, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "Perform comprehensive read-only diagnostics on Trailytics." in result.output


def test_doctor_all_checks_pass(cli_runner, mock_repo_dir):
    """Verify 'trailytics doctor' passes all categories when environment is fully healthy."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "git" in cmd and "rev-parse" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="28192d8ffe85299f5c44032f705a9e518e6d1189\n", stderr="")
        if "git" in cmd and "status" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        if "docker" in cmd and "--version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker version 26.1.4\n", stderr="")
        if "docker" in cmd and "info" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Server Version: 26.1.4\n", stderr="")
        if "docker" in cmd and "compose" in cmd and "version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker Compose version v2.27.1\n", stderr="")
        if "docker" in cmd and "config" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        if "docker" in cmd and "ps" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        if "docker" in cmd and "inspect" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="running|healthy|0\n", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_resp = mock.MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run), \
         mock.patch("urllib.request.urlopen", return_value=mock_resp):

        result = cli_runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "Trailytics Doctor" in result.output
        assert "Repository" in result.output
        assert "Docker" in result.output
        assert "Deployment" in result.output
        assert "Connectivity" in result.output
        assert "All 15 checks passed" in result.output or "All" in result.output


def test_doctor_categories_represented(cli_runner, mock_repo_dir):
    """Verify all 4 required diagnostic categories are represented in the output."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "docker" in cmd and "inspect" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="exited|none|0\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run):

        result = cli_runner.invoke(cli, ["doctor"])
        assert "Repository" in result.output
        assert "Docker" in result.output
        assert "Deployment" in result.output
        assert "Connectivity" in result.output


def test_doctor_stopped_deployment_renders_warn_and_exits_zero(cli_runner, mock_repo_dir):
    """Verify stopped deployment renders WARN, skips connectivity, and exits 0."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "git" in cmd and "rev-parse" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="28192d8ffe85299f5c44032f705a9e518e6d1189\n")
        if "git" in cmd and "status" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "ps" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "inspect" in cmd:
            # All containers are stopped
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="exited|none|0\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok")

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run):

        result = cli_runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "[WARN] Runtime services healthy" in result.output
        assert "Deployment is stopped" in result.output
        assert "[SKIP] Dashboard reachable" in result.output
        assert "[SKIP] Backend API reachable" in result.output
        assert "Completed with 1 warning" in result.output


def test_doctor_docker_unavailable_renders_skip_and_fails(cli_runner, mock_repo_dir):
    """Verify when Docker is unavailable, dependent checks skip and doctor exits 1."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "git" in cmd and "rev-parse" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="28192d8ffe85299f5c44032f705a9e518e6d1189\n")
        if "git" in cmd and "status" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "--version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker version 26.1.4\n")
        if "docker" in cmd and "info" in cmd:
            # Daemon down
            return subprocess.CompletedProcess(args=cmd, returncode=1, stderr="Cannot connect to the Docker daemon")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run):

        result = cli_runner.invoke(cli, ["doctor"])
        assert result.exit_code == 1
        assert "[FAIL] Docker daemon available" in result.output
        assert "[SKIP] Compose configuration valid" in result.output
        assert "[SKIP] Project identity verified" in result.output
        assert "[SKIP] Runtime services healthy" in result.output
        assert "failed" in result.output


def test_doctor_submodule_mismatch_fails_but_runs_independent_checks(cli_runner, mock_repo_dir):
    """Verify failure in one check (submodule commit mismatch) does not halt other checks."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "git" in cmd and "rev-parse" in cmd:
            # Different commit
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="1111111111111111111111111111111111111111\n")
        if "git" in cmd and "status" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "--version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker version 26.1.4\n")
        if "docker" in cmd and "info" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Server Version: 26.1.4\n")
        if "docker" in cmd and "compose" in cmd and "version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker Compose version v2.27.1\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run):

        result = cli_runner.invoke(cli, ["doctor"])
        assert result.exit_code == 1
        assert "[FAIL] Pinned Opik commit verified" in result.output
        # Docker checks still ran independently!
        assert "[PASS] Docker CLI installed" in result.output
        assert "[PASS] Docker daemon available" in result.output


def test_doctor_sensitive_values_not_printed(cli_runner, mock_repo_dir):
    """Verify secrets or passwords in environment files are never displayed."""
    # Write sensitive credentials to env file
    env_content = (mock_repo_dir / "config" / "trailytics.env").read_text()
    (mock_repo_dir / "config" / "trailytics.env").write_text(
        env_content + "\nSECRET_KEY=supersecret123\nMYSQL_PASSWORD=mysupersecretpass\n"
    )

    def fake_subprocess_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run):

        result = cli_runner.invoke(cli, ["doctor"])
        assert "supersecret123" not in result.output
        assert "mysupersecretpass" not in result.output


def test_doctor_unhealthy_container_fails(cli_runner, mock_repo_dir):
    """Verify if a container is unhealthy, doctor reports FAIL and exits 1."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "git" in cmd and "rev-parse" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="28192d8ffe85299f5c44032f705a9e518e6d1189\n")
        if "git" in cmd and "status" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "inspect" in cmd:
            if "backend" in cmd[-1]:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="running|unhealthy|0\n")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="running|healthy|0\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok")

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run):

        result = cli_runner.invoke(cli, ["doctor"])
        assert result.exit_code == 1
        assert "[FAIL] Runtime services healthy" in result.output
        assert "unhealthy" in result.output


def test_doctor_connectivity_failure_when_running(cli_runner, mock_repo_dir):
    """Verify connectivity failure when deployment is running causes FAIL and exit 1."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "git" in cmd and "rev-parse" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="28192d8ffe85299f5c44032f705a9e518e6d1189\n")
        if "git" in cmd and "status" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "inspect" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="running|healthy|0\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok")

    with mock.patch("trailytics.cli.commands.doctor.find_repository_root", return_value=mock_repo_dir), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run), \
         mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):

        result = cli_runner.invoke(cli, ["doctor"])
        assert result.exit_code == 1
        assert "[FAIL] Dashboard reachable" in result.output
        assert "[FAIL] Backend API reachable" in result.output
        assert "Connection refused" in result.output


def test_doctor_standalone_mode_project_identity_pass(cli_runner):
    """Verify in standalone mode that single directory container sets pass project identity."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "docker" in cmd and "--version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker version 25.0.0\n")
        if "docker" in cmd and "info" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Server Version: 25.0.0\n")
        if "docker" in cmd and "compose" in cmd and "version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker Compose version v2.24.0\n")
        if "docker" in cmd and "compose" in cmd and "config" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "ps" in cmd and "label=com.docker.compose.project=opik-opik" in cmd:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="/some/deployment/docker-compose\n/some/deployment/docker-compose\n",
            )
        if "docker" in cmd and "inspect" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="running|healthy|0\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")

    mock_resp = mock.MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with mock.patch("trailytics.cli.commands.doctor.is_development_mode", return_value=False), \
         mock.patch("trailytics.cli.commands.doctor.check_standalone_package", return_value=[]), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run), \
         mock.patch("urllib.request.urlopen", return_value=mock_resp):

        result = cli_runner.invoke(cli, ["doctor"])
        assert "Trailytics Doctor (Mode: Standalone)" in result.output
        assert "[PASS] Project identity verified" in result.output
        assert "Project 'opik-opik' is isolated and consistent" in result.output


def test_doctor_standalone_mode_project_identity_split_conflict(cli_runner):
    """Verify in standalone mode that containers from multiple working directories fail."""
    def fake_subprocess_run(cmd, *args, **kwargs):
        if "docker" in cmd and "--version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker version 25.0.0\n")
        if "docker" in cmd and "info" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Server Version: 25.0.0\n")
        if "docker" in cmd and "compose" in cmd and "version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Docker Compose version v2.24.0\n")
        if "docker" in cmd and "compose" in cmd and "config" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")
        if "docker" in cmd and "ps" in cmd and "label=com.docker.compose.project=opik-opik" in cmd:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="/first/dir\n/second/dir\n",
            )
        if "docker" in cmd and "inspect" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="running|healthy|0\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")

    mock_resp = mock.MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with mock.patch("trailytics.cli.commands.doctor.is_development_mode", return_value=False), \
         mock.patch("trailytics.cli.commands.doctor.check_standalone_package", return_value=[]), \
         mock.patch("subprocess.run", side_effect=fake_subprocess_run), \
         mock.patch("urllib.request.urlopen", return_value=mock_resp):

        result = cli_runner.invoke(cli, ["doctor"])
        assert "Trailytics Doctor (Mode: Standalone)" in result.output
        assert "[FAIL] Project identity verified" in result.output
        assert "Conflicting containers detected across multiple directories" in result.output



