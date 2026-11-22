"""Unit tests for Trailytics Profile models and validation."""

from __future__ import annotations

import pytest

from trailytics.exceptions import ProfileValidationError
from trailytics.profiles.models import Profile, ResolvedConfig


def test_valid_profile_creation():
    """Verify creating a valid profile succeeds and normalizes fields."""
    p = Profile(
        name="production",
        type="REMOTE",
        url="https://trailytics.company.com/api",
        workspace="production-ai",
        default_project="My Project",
        description="Production instance",
    )
    p.validate()
    assert p.name == "production"
    assert p.type == "remote"
    assert p.url == "https://trailytics.company.com/api"
    assert p.workspace == "production-ai"
    assert p.default_project == "My Project"


def test_profile_empty_name():
    """Verify empty name raises ProfileValidationError."""
    with pytest.raises(ProfileValidationError, match="name cannot be empty"):
        Profile(name="").validate()


def test_profile_name_too_long():
    """Verify names over 64 chars raise ProfileValidationError."""
    long_name = "a" * 65
    with pytest.raises(ProfileValidationError, match="exceeds maximum length"):
        Profile(name=long_name).validate()


def test_profile_name_invalid_characters():
    """Verify invalid characters in name raise ProfileValidationError."""
    for invalid in ["prod.env", "my profile", "prod/env", "test@123", "prod!"]:
        with pytest.raises(ProfileValidationError, match="Invalid profile name"):
            Profile(name=invalid).validate()


def test_profile_reserved_names():
    """Verify reserved names are rejected."""
    for reserved in ["default_profile", "profiles", "DEFAULT_PROFILE"]:
        with pytest.raises(ProfileValidationError, match="reserved and cannot be used"):
            Profile(name=reserved).validate()


def test_profile_invalid_type():
    """Verify invalid profile types are rejected."""
    with pytest.raises(ProfileValidationError, match="Invalid profile type"):
        Profile(name="test", type="kubernetes").validate()


def test_profile_invalid_url():
    """Verify invalid URLs are rejected."""
    # Missing scheme
    with pytest.raises(ProfileValidationError, match="URL must begin with 'http://' or 'https://'"):
        Profile(name="test", url="localhost:5173/api").validate()

    # Unsupported scheme
    with pytest.raises(ProfileValidationError, match="URL must begin with 'http://' or 'https://'"):
        Profile(name="test", url="ftp://example.com").validate()

    # Empty host
    with pytest.raises(ProfileValidationError, match="URL must include a host/domain name"):
        Profile(name="test", url="http://").validate()


def test_profile_to_dict_and_from_dict():
    """Verify dictionary serialization and deserialization."""
    p = Profile(
        name="staging",
        type="remote",
        url="https://staging.company.com/api",
        workspace="staging-ws",
        default_project="Staging Project",
        description="Staging cluster",
    )
    p.validate()
    data = p.to_dict()
    assert data["type"] == "remote"
    assert data["url"] == "https://staging.company.com/api"

    restored = Profile.from_dict("staging", data)
    assert restored.name == "staging"
    assert restored.type == "remote"
    assert restored.url == p.url
    assert restored.workspace == p.workspace
    assert restored.default_project == p.default_project


def test_resolved_config_dataclass():
    """Verify ResolvedConfig dataclass instantiation."""
    rc = ResolvedConfig(
        profile_name="prod",
        type="remote",
        url="https://example.com/api",
        workspace="ws",
        project="proj",
        api_key="secret",
        has_api_key=True,
        sources={"url": "cli", "api_key": "environment:TRAILYTICS_API_KEY"},
    )
    assert rc.profile_name == "prod"
    assert rc.type == "remote"
    assert rc.has_api_key is True
    assert rc.sources["url"] == "cli"
