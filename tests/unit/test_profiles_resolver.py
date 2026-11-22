"""Unit tests for Trailytics configuration resolution and precedence hierarchy."""

from __future__ import annotations

import os
import pytest

from trailytics.exceptions import ProfileNotFoundError
from trailytics.profiles.models import Profile
from trailytics.profiles.resolver import ConfigResolver, resolve_config
from trailytics.profiles.storage import ProfileStorage


@pytest.fixture
def configured_storage(tmp_path):
    """Storage fixture populated with sample profiles."""
    storage = ProfileStorage(config_dir=tmp_path / "cfg")
    p_dev = Profile(
        name="dev",
        type="local",
        url="http://localhost:5173/api",
        workspace="dev-ws",
        default_project="Dev Project",
    )
    p_prod = Profile(
        name="prod",
        type="remote",
        url="https://prod.company.com/api",
        workspace="prod-ws",
        default_project="Prod Project",
    )
    storage.create_profile(p_dev, set_default=True)
    storage.create_profile(p_prod, api_key="stored-prod-key")
    return storage


def test_builtin_fallback_when_no_profiles_configured(tmp_path):
    """Verify built-in local fallback when storage has no profiles configured."""
    empty_storage = ProfileStorage(config_dir=tmp_path / "empty")
    res = resolve_config(storage=empty_storage)

    assert res.profile_name == "local"
    assert res.type == "local"
    assert res.url == "http://localhost:5173/api"
    assert res.workspace == "default"
    assert res.project == "Default Project"
    assert res.api_key is None
    assert res.has_api_key is False


def test_default_profile_precedence(configured_storage):
    """Verify configured default profile is selected when no flag or env var is present."""
    res = resolve_config(storage=configured_storage)
    assert res.profile_name == "dev"
    assert res.url == "http://localhost:5173/api"
    assert res.workspace == "dev-ws"
    assert res.project == "Dev Project"


def test_env_profile_override(configured_storage, monkeypatch):
    """Verify TRAILYTICS_PROFILE overrides default_profile."""
    monkeypatch.setenv("TRAILYTICS_PROFILE", "prod")
    res = resolve_config(storage=configured_storage)

    assert res.profile_name == "prod"
    assert res.type == "remote"
    assert res.url == "https://prod.company.com/api"
    assert res.workspace == "prod-ws"
    assert res.project == "Prod Project"
    assert res.api_key == "stored-prod-key"
    assert res.has_api_key is True


def test_cli_profile_override(configured_storage, monkeypatch):
    """Verify CLI --profile overrides both TRAILYTICS_PROFILE and default_profile."""
    monkeypatch.setenv("TRAILYTICS_PROFILE", "dev")
    res = resolve_config(cli_profile="prod", storage=configured_storage)

    assert res.profile_name == "prod"
    assert res.url == "https://prod.company.com/api"
    assert res.api_key == "stored-prod-key"


def test_nonexistent_profile_raises_error(configured_storage):
    """Verify requesting a non-existent profile raises ProfileNotFoundError."""
    with pytest.raises(ProfileNotFoundError, match="Profile 'staging' does not exist"):
        resolve_config(cli_profile="staging", storage=configured_storage)


def test_url_precedence_hierarchy(configured_storage, monkeypatch):
    """Verify URL precedence: CLI > TRAILYTICS_URL > OPIK_URL_OVERRIDE > profile > default."""
    # 1. Profile URL
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.url == "https://prod.company.com/api"

    # 2. OPIK_URL_OVERRIDE overrides profile
    monkeypatch.setenv("OPIK_URL_OVERRIDE", "http://opik.env/api")
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.url == "http://opik.env/api"

    # 3. TRAILYTICS_URL overrides OPIK_URL_OVERRIDE
    monkeypatch.setenv("TRAILYTICS_URL", "http://trailytics.env/api")
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.url == "http://trailytics.env/api"

    # 4. CLI flag overrides TRAILYTICS_URL
    res = resolve_config(
        cli_profile="prod",
        cli_url="http://cli.flag/api",
        storage=configured_storage,
    )
    assert res.url == "http://cli.flag/api"


def test_workspace_precedence_hierarchy(configured_storage, monkeypatch):
    """Verify Workspace precedence: CLI > TRAILYTICS_WORKSPACE > OPIK_WORKSPACE > profile."""
    # 1. Profile workspace
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.workspace == "prod-ws"

    # 2. OPIK_WORKSPACE
    monkeypatch.setenv("OPIK_WORKSPACE", "opik-ws")
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.workspace == "opik-ws"

    # 3. TRAILYTICS_WORKSPACE
    monkeypatch.setenv("TRAILYTICS_WORKSPACE", "trailytics-ws")
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.workspace == "trailytics-ws"

    # 4. CLI flag
    res = resolve_config(
        cli_profile="prod",
        cli_workspace="cli-ws",
        storage=configured_storage,
    )
    assert res.workspace == "cli-ws"


def test_api_key_precedence_hierarchy(configured_storage, monkeypatch):
    """Verify API key precedence: CLI > TRAILYTICS_API_KEY > OPIK_API_KEY > credentials.toml."""
    # 1. Stored in credentials.toml
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.api_key == "stored-prod-key"

    # 2. OPIK_API_KEY overrides stored credential
    monkeypatch.setenv("OPIK_API_KEY", "env-opik-key")
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.api_key == "env-opik-key"

    # 3. TRAILYTICS_API_KEY overrides OPIK_API_KEY
    monkeypatch.setenv("TRAILYTICS_API_KEY", "env-trailytics-key")
    res = resolve_config(cli_profile="prod", storage=configured_storage)
    assert res.api_key == "env-trailytics-key"

    # 4. CLI flag overrides TRAILYTICS_API_KEY
    res = resolve_config(
        cli_profile="prod",
        cli_api_key="cli-key",
        storage=configured_storage,
    )
    assert res.api_key == "cli-key"
