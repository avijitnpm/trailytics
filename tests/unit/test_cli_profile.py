"""Unit tests for Trailytics CLI profile management commands."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from click.testing import CliRunner

from trailytics.cli.main import cli
from trailytics.profiles.storage import ProfileStorage


@pytest.fixture
def isolated_cli(tmp_path, monkeypatch):
    """Setup CLI runner with isolated config and HOME directories."""
    config_dir = tmp_path / "trailytics_home" / ".trailytics"
    monkeypatch.setenv("TRAILYTICS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HOME", str(tmp_path / "trailytics_home"))
    runner = CliRunner()
    return runner, config_dir


def test_cli_profile_help(isolated_cli):
    """Verify 'trailytics profile --help' lists available subcommands."""
    runner, _ = isolated_cli
    result = runner.invoke(cli, ["profile", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output
    assert "show" in result.output
    assert "use" in result.output
    assert "delete" in result.output


def test_profile_list_empty(isolated_cli):
    """Verify 'trailytics profile list' output when no profiles are configured."""
    runner, _ = isolated_cli
    result = runner.invoke(cli, ["profile", "list"])
    assert result.exit_code == 0
    assert "No profiles configured" in result.output
    assert "local" in result.output


def test_profile_create_without_api_key(isolated_cli):
    """Verify creating a profile with --no-api-key."""
    runner, config_dir = isolated_cli
    result = runner.invoke(
        cli,
        [
            "profile",
            "create",
            "staging",
            "--type",
            "remote",
            "--url",
            "https://staging.company.com/api",
            "--workspace",
            "qa-workspace",
            "--description",
            "Staging cluster",
            "--no-api-key",
        ],
    )
    assert result.exit_code == 0
    assert "Profile 'staging' created successfully." in result.output

    storage = ProfileStorage(config_dir=config_dir)
    profile = storage.get_profile("staging")
    assert profile is not None
    assert profile.name == "staging"
    assert profile.url == "https://staging.company.com/api"
    assert profile.workspace == "qa-workspace"
    assert storage.has_credential("staging") is False


def test_profile_create_with_interactive_api_key(isolated_cli):
    """Verify creating a profile securely prompts for API key and does not leak it."""
    runner, config_dir = isolated_cli
    secret_key = "trl_secret_token_xyz999"

    result = runner.invoke(
        cli,
        [
            "profile",
            "create",
            "production",
            "--type",
            "remote",
            "--url",
            "https://production.company.com/api",
        ],
        input=f"{secret_key}\n",
    )
    assert result.exit_code == 0
    assert "Profile 'production' created successfully." in result.output

    # CRITICAL SECURITY CHECK: Secret API key must NEVER appear in output
    assert secret_key not in result.output

    # Verify key is in credentials.toml
    storage = ProfileStorage(config_dir=config_dir)
    assert storage.has_credential("production") is True
    assert storage.get_credential("production") == secret_key

    # Verify key is NOT in config.toml
    assert secret_key not in (config_dir / "config.toml").read_text()


def test_profile_create_duplicate_rejected(isolated_cli):
    """Verify duplicate profile names are rejected with error."""
    runner, _ = isolated_cli
    # First create
    runner.invoke(
        cli,
        ["profile", "create", "env1", "--url", "https://env1.com/api", "--no-api-key"],
    )
    # Second create with same name
    result = runner.invoke(
        cli,
        ["profile", "create", "env1", "--url", "https://env2.com/api", "--no-api-key"],
    )
    assert result.exit_code == 1
    assert "Error: Profile 'env1' already exists" in result.output


def test_profile_create_invalid_name(isolated_cli):
    """Verify invalid profile name is rejected."""
    runner, _ = isolated_cli
    result = runner.invoke(
        cli,
        ["profile", "create", "bad name with space", "--no-api-key"],
    )
    assert result.exit_code == 1
    assert "Invalid profile name" in result.output


def test_profile_create_invalid_url(isolated_cli):
    """Verify invalid profile URL is rejected."""
    runner, _ = isolated_cli
    result = runner.invoke(
        cli,
        ["profile", "create", "badurl", "--url", "invalid-no-scheme", "--no-api-key"],
    )
    assert result.exit_code == 1
    assert "Invalid URL" in result.output


def test_profile_list_populated(isolated_cli):
    """Verify 'profile list' displays table with correct columns and no API keys."""
    runner, _ = isolated_cli
    runner.invoke(cli, ["profile", "create", "p1", "--url", "https://p1.com/api", "--no-api-key"])
    runner.invoke(cli, ["profile", "create", "p2", "--url", "https://p2.com/api"], input="secret_p2\n")

    result = runner.invoke(cli, ["profile", "list"])
    assert result.exit_code == 0
    assert "p1" in result.output
    assert "p2" in result.output
    assert "https://p1.com/api" in result.output
    assert "https://p2.com/api" in result.output
    assert "secret_p2" not in result.output


def test_profile_show_existing_and_credentials_status(isolated_cli):
    """Verify 'profile show' outputs details and never prints the API key value."""
    runner, _ = isolated_cli
    secret_key = "trl_secret_key_prod_abc"
    runner.invoke(
        cli,
        [
            "profile",
            "create",
            "prod",
            "--url",
            "https://prod.company.com/api",
            "--workspace",
            "analytics",
            "--description",
            "Production telemetry",
        ],
        input=f"{secret_key}\n",
    )

    result = runner.invoke(cli, ["profile", "show", "prod"])
    assert result.exit_code == 0
    assert "Profile:           prod" in result.output
    assert "URL:               https://prod.company.com/api" in result.output
    assert "Workspace:         analytics" in result.output
    assert "Description:       Production telemetry" in result.output
    assert "API Key:           Configured" in result.output
    # MUST NOT LEAK SECRET
    assert secret_key not in result.output


def test_profile_show_builtin_local(isolated_cli):
    """Verify 'profile show local' displays built-in local configuration even if not in config.toml."""
    runner, _ = isolated_cli
    result = runner.invoke(cli, ["profile", "show", "local"])
    assert result.exit_code == 0
    assert "Profile:           local" in result.output
    assert "http://localhost:5173/api" in result.output
    assert "Type:              local" in result.output


def test_profile_show_nonexistent(isolated_cli):
    """Verify 'profile show' on unknown profile fails with exit code 1."""
    runner, _ = isolated_cli
    result = runner.invoke(cli, ["profile", "show", "unknown"])
    assert result.exit_code == 1
    assert "Error: Profile 'unknown' does not exist" in result.output


def test_profile_use(isolated_cli, config_dir=None):
    """Verify 'profile use' switches the persistent default profile."""
    runner, config_dir = isolated_cli
    runner.invoke(cli, ["profile", "create", "p1", "--no-api-key"])
    runner.invoke(cli, ["profile", "create", "p2", "--no-api-key"])

    storage = ProfileStorage(config_dir=config_dir)
    assert storage.get_default_profile_name() == "p1"

    result = runner.invoke(cli, ["profile", "use", "p2"])
    assert result.exit_code == 0
    assert "Default profile set to 'p2'." in result.output
    assert storage.get_default_profile_name() == "p2"

    # Using non-existent profile fails
    fail_result = runner.invoke(cli, ["profile", "use", "missing"])
    assert fail_result.exit_code == 1
    assert "Error: Profile 'missing' does not exist" in fail_result.output


def test_profile_delete_with_confirmation_and_flags(isolated_cli):
    """Verify 'profile delete' with confirmation prompt and --yes flag."""
    runner, config_dir = isolated_cli
    runner.invoke(cli, ["profile", "create", "p1", "--no-api-key"])
    runner.invoke(cli, ["profile", "create", "p2", "--no-api-key"])
    runner.invoke(cli, ["profile", "create", "p3", "--no-api-key"])

    storage = ProfileStorage(config_dir=config_dir)
    storage.set_default_profile_name("p1")

    # 1. Aborted deletion with 'n'
    abort_res = runner.invoke(cli, ["profile", "delete", "p2"], input="n\n")
    assert abort_res.exit_code == 0
    assert "Aborted." in abort_res.output
    assert storage.get_profile("p2") is not None

    # 2. Confirmed deletion with 'y'
    confirm_res = runner.invoke(cli, ["profile", "delete", "p2"], input="y\n")
    assert confirm_res.exit_code == 0
    assert "Profile 'p2' deleted successfully." in confirm_res.output
    assert storage.get_profile("p2") is None

    # 3. Deletion with -y flag
    flag_res = runner.invoke(cli, ["profile", "delete", "p3", "-y"])
    assert flag_res.exit_code == 0
    assert "Profile 'p3' deleted successfully." in flag_res.output
    assert storage.get_profile("p3") is None


def test_profile_delete_default_protection(isolated_cli):
    """Verify attempting to delete default profile when others exist is blocked."""
    runner, config_dir = isolated_cli
    runner.invoke(cli, ["profile", "create", "p1", "--no-api-key"])
    runner.invoke(cli, ["profile", "create", "p2", "--no-api-key"])

    storage = ProfileStorage(config_dir=config_dir)
    storage.set_default_profile_name("p1")

    result = runner.invoke(cli, ["profile", "delete", "p1", "-y"])
    assert result.exit_code == 1
    assert "Cannot delete the default profile 'p1'" in result.output


def test_profile_delete_nonexistent(isolated_cli):
    """Verify deleting a non-existent profile fails."""
    runner, _ = isolated_cli
    result = runner.invoke(cli, ["profile", "delete", "nonexistent", "-y"])
    assert result.exit_code == 1
    assert "Error: Profile 'nonexistent' does not exist" in result.output


def test_global_profile_option_passed_to_context(isolated_cli):
    """Verify root CLI accepts --profile flag without errors."""
    runner, _ = isolated_cli
    result = runner.invoke(cli, ["--profile", "custom", "--help"])
    assert result.exit_code == 0
    assert "Trailytics - AI Observability & Tracing CLI." in result.output
