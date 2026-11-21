"""Unit tests for Trailytics CLI, repository discovery, and subprocess runner."""

import os
from pathlib import Path
import subprocess
from unittest import mock
import pytest
from click.testing import CliRunner

import trailytics
from trailytics.cli.main import cli
from trailytics.cli.runner import (
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
    (repo / "trailytics" / "start.sh").write_text("#!/bin/bash\necho mock start\n")
    (repo / "trailytics" / "start.sh").chmod(0o755)
    (repo / "config").mkdir()
    (repo / "config" / "trailytics.env").write_text(
        "OPIK_VERSION=2.2.138\n"
        "OPIK_COMMIT=28192d8ffe85299f5c44032f705a9e518e6d1189\n"
        "TRAILYTICS_COMPOSE_PROJECT=opik-opik\n"
    )
    (repo / "upstream" / "opik").mkdir(parents=True)
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
