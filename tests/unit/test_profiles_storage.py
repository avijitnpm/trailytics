"""Unit tests for Trailytics ProfileStorage and secure credentials management."""

from __future__ import annotations

import os
import stat
import pytest

from trailytics.exceptions import (
    ProfileAlreadyExistsError,
    ProfileNotFoundError,
    ProfileStorageError,
    ProfileValidationError,
)
from trailytics.profiles.models import Profile
from trailytics.profiles.storage import ProfileStorage


@pytest.fixture
def test_storage(tmp_path):
    """Create ProfileStorage instance backed by isolated temporary directory."""
    config_dir = tmp_path / "trailytics_config"
    return ProfileStorage(config_dir=config_dir)


def test_initial_storage_does_not_create_files(test_storage):
    """Verify reading from uninitialized storage does not create files on disk."""
    assert not test_storage.config_path.exists()
    assert not test_storage.credentials_path.exists()
    assert test_storage.list_profiles() == {}
    assert test_storage.get_default_profile_name() == "local"
    assert not test_storage.config_path.exists()


def test_create_profile_without_credentials(test_storage):
    """Verify creating a profile without an API key."""
    profile = Profile(
        name="prod",
        type="remote",
        url="https://prod.company.com/api",
        workspace="prod-ws",
        default_project="Main Project",
    )
    test_storage.create_profile(profile)

    assert test_storage.config_path.exists()
    assert not test_storage.credentials_path.exists()

    loaded = test_storage.get_profile("prod")
    assert loaded is not None
    assert loaded.name == "prod"
    assert loaded.url == "https://prod.company.com/api"
    assert test_storage.get_default_profile_name() == "prod"
    assert test_storage.get_credential("prod") is None


def test_create_profile_with_credentials_and_file_mode(test_storage):
    """Verify creating a profile with an API key enforces 0600 file permissions."""
    profile = Profile(
        name="prod",
        type="remote",
        url="https://prod.company.com/api",
    )
    test_storage.create_profile(profile, api_key="test_secret_key_123")

    assert test_storage.config_path.exists()
    assert test_storage.credentials_path.exists()

    # 1. Verify credentials NOT in config.toml
    config_text = test_storage.config_path.read_text()
    assert "test_secret_key_123" not in config_text

    # 2. Verify credentials in credentials.toml
    assert test_storage.has_credential("prod") is True
    assert test_storage.get_credential("prod") == "test_secret_key_123"

    # 3. Verify POSIX 0600 file permissions
    if os.name == "posix":
        mode = stat.S_IMODE(os.stat(test_storage.credentials_path).st_mode)
        assert mode == 0o600


def test_duplicate_profile_rejection(test_storage):
    """Verify creating a profile with an existing name is rejected."""
    profile = Profile(name="staging", url="https://staging.company.com/api")
    test_storage.create_profile(profile)

    duplicate = Profile(name="staging", url="https://other.company.com/api")
    with pytest.raises(ProfileAlreadyExistsError, match="Profile 'staging' already exists"):
        test_storage.create_profile(duplicate)


def test_multiple_profiles_and_isolation(test_storage):
    """Verify managing multiple profiles preserves independent settings."""
    p1 = Profile(name="dev", url="http://localhost:5173/api", type="local")
    p2 = Profile(name="qa", url="https://qa.company.com/api", type="remote")
    p3 = Profile(name="prod", url="https://prod.company.com/api", type="remote")

    test_storage.create_profile(p1, set_default=True)
    test_storage.create_profile(p2, api_key="qa-key")
    test_storage.create_profile(p3, api_key="prod-key")

    profiles = test_storage.list_profiles()
    assert len(profiles) == 3
    assert set(profiles.keys()) == {"dev", "qa", "prod"}
    assert test_storage.get_default_profile_name() == "dev"

    assert test_storage.get_credential("qa") == "qa-key"
    assert test_storage.get_credential("prod") == "prod-key"
    assert test_storage.get_credential("dev") is None

    # Delete qa profile
    test_storage.delete_profile("qa")
    remaining = test_storage.list_profiles()
    assert "qa" not in remaining
    assert set(remaining.keys()) == {"dev", "prod"}
    assert test_storage.get_credential("qa") is None
    assert test_storage.get_credential("prod") == "prod-key"


def test_cannot_delete_default_profile_when_others_exist(test_storage):
    """Verify default profile cannot be deleted if other profiles exist."""
    p1 = Profile(name="p1", url="http://localhost:5173/api")
    p2 = Profile(name="p2", url="https://p2.com/api")

    test_storage.create_profile(p1, set_default=True)
    test_storage.create_profile(p2)

    with pytest.raises(ProfileValidationError, match="Cannot delete default profile"):
        test_storage.delete_profile("p1")

    # Change default to p2, then deleting p1 succeeds
    test_storage.set_default_profile_name("p2")
    test_storage.delete_profile("p1")
    assert test_storage.get_profile("p1") is None


def test_set_default_profile_validation(test_storage):
    """Verify setting non-existent profile as default fails."""
    with pytest.raises(ProfileNotFoundError, match="does not exist"):
        test_storage.set_default_profile_name("non_existent")


def test_credentials_permission_correction_on_read(test_storage):
    """Verify existing permissive credentials file permissions are corrected to 0600 on read."""
    if os.name != "posix":
        pytest.skip("POSIX only test")

    test_storage.config_dir.mkdir(parents=True, exist_ok=True)
    test_storage.credentials_path.write_text('[profiles.prod]\napi_key = "secret"\n')
    # Intentionally loosen permissions to 0644
    os.chmod(test_storage.credentials_path, 0o644)
    assert stat.S_IMODE(os.stat(test_storage.credentials_path).st_mode) == 0o644

    # Trigger read
    key = test_storage.get_credential("prod")
    assert key == "secret"

    # Verify mode was corrected to 0600
    corrected_mode = stat.S_IMODE(os.stat(test_storage.credentials_path).st_mode)
    assert corrected_mode == 0o600


def test_malformed_config_file_raises_error(test_storage):
    """Verify corrupted config file raises ProfileStorageError."""
    test_storage.config_dir.mkdir(parents=True, exist_ok=True)
    test_storage.config_path.write_text("invalid [[ toml == syntax")
    with pytest.raises(ProfileStorageError):
        test_storage.list_profiles()
