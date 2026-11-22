"""Profile and credential storage manager for Trailytics."""

from __future__ import annotations

import os
import stat
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, Optional

from trailytics.exceptions import (
    InsecureCredentialsError,
    ProfileAlreadyExistsError,
    ProfileNotFoundError,
    ProfileStorageError,
    ProfileValidationError,
)
from trailytics.profiles.models import Profile
from trailytics.profiles.toml import dumps_toml, load_toml_file


class ProfileStorage:
    """Manages persistent profile configurations and secure credentials storage."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        if config_dir is not None:
            self.config_dir = Path(config_dir).resolve()
        else:
            override_dir = os.environ.get("TRAILYTICS_CONFIG_DIR")
            if override_dir:
                self.config_dir = Path(override_dir).resolve()
            else:
                self.config_dir = (Path.home() / ".trailytics").resolve()

        self.config_path = self.config_dir / "config.toml"
        self.credentials_path = self.config_dir / "credentials.toml"

    # =========================================================================
    # Safe File Operations
    # =========================================================================

    def _safe_write_file(self, path: Path, content: str, mode: int = 0o644) -> None:
        """Write content to path atomically using a temporary file."""
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Create temporary file in the same directory for atomic rename
        fd, tmp_path_str = tempfile.mkstemp(
            dir=str(self.config_dir),
            prefix=".tmp_",
            suffix=".toml",
        )
        tmp_path = Path(tmp_path_str)

        try:
            if os.name == "posix":
                try:
                    os.fchmod(fd, mode)
                except OSError:
                    pass

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

            if os.name == "posix":
                try:
                    os.chmod(tmp_path, mode)
                except OSError:
                    pass

            os.replace(tmp_path, path)

            if os.name == "posix":
                try:
                    os.chmod(path, mode)
                except OSError:
                    pass
        except Exception as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise ProfileStorageError(f"Failed to write file {path}: {e}") from e

    def _check_and_enforce_credentials_permissions(self) -> None:
        """Verify and enforce 0600 permissions on credentials.toml on POSIX."""
        if not self.credentials_path.is_file() or os.name != "posix":
            return

        try:
            st = os.stat(self.credentials_path)
            current_mode = stat.S_IMODE(st.st_mode)
            if current_mode != 0o600:
                try:
                    os.chmod(self.credentials_path, 0o600)
                except OSError as e:
                    warnings.warn(
                        f"Credentials file {self.credentials_path} has permissions "
                        f"{oct(current_mode)}, expected 0600. Failed to update: {e}",
                        UserWarning,
                        stacklevel=2,
                    )
        except OSError as e:
            warnings.warn(
                f"Could not inspect credentials file permissions: {e}",
                UserWarning,
                stacklevel=2,
            )

    # =========================================================================
    # Configuration (config.toml) Operations
    # =========================================================================

    def _load_config_raw(self) -> Dict[str, Any]:
        """Load raw config.toml data."""
        return load_toml_file(self.config_path)

    def _save_config_raw(self, data: Dict[str, Any]) -> None:
        """Save raw config.toml data."""
        # Ensure credentials are NEVER saved in config.toml
        profiles = data.get("profiles", {})
        for name, p_data in profiles.items():
            if isinstance(p_data, dict) and "api_key" in p_data:
                del p_data["api_key"]

        content = dumps_toml(data)
        self._safe_write_file(self.config_path, content, mode=0o644)

    def get_default_profile_name(self) -> str:
        """Get the configured default profile name, defaulting to 'local'."""
        data = self._load_config_raw()
        return str(data.get("default_profile", "local"))

    def set_default_profile_name(self, name: str) -> None:
        """Set the default profile name in config.toml."""
        name = name.strip()
        data = self._load_config_raw()
        profiles = data.get("profiles", {})

        if name not in profiles and name != "local":
            raise ProfileNotFoundError(
                f"Profile '{name}' does not exist. Cannot set as default."
            )

        data["default_profile"] = name
        self._save_config_raw(data)

    def list_profiles(self) -> Dict[str, Profile]:
        """List all configured profiles as a dict of {name: Profile}."""
        data = self._load_config_raw()
        profiles_raw = data.get("profiles", {})
        result: Dict[str, Profile] = {}

        if not isinstance(profiles_raw, dict):
            return result

        for name, p_data in profiles_raw.items():
            if isinstance(p_data, dict):
                try:
                    result[name] = Profile.from_dict(name, p_data)
                except ProfileValidationError as e:
                    # Invalid profile entry in config file
                    raise ProfileStorageError(
                        f"Profile '{name}' in {self.config_path} is invalid: {e}"
                    ) from e

        return result

    def get_profile(self, name: str) -> Optional[Profile]:
        """Get a profile by name, or None if it does not exist."""
        name = name.strip()
        profiles = self.list_profiles()
        return profiles.get(name)

    def create_profile(
        self,
        profile: Profile,
        api_key: Optional[str] = None,
        set_default: bool = False,
    ) -> None:
        """Create a new profile. Rejects duplicate profile names."""
        profile.validate()

        data = self._load_config_raw()
        profiles = data.setdefault("profiles", {})

        if profile.name in profiles:
            raise ProfileAlreadyExistsError(
                f"Profile '{profile.name}' already exists. "
                f"Use 'trailytics profile show {profile.name}' or choose a different name."
            )

        is_first_profile = len(profiles) == 0
        profiles[profile.name] = profile.to_dict()

        if set_default or is_first_profile or "default_profile" not in data:
            data["default_profile"] = profile.name

        self._save_config_raw(data)

        # Store API key in credentials.toml if provided
        if api_key:
            self.set_credential(profile.name, api_key)

    def delete_profile(self, name: str) -> None:
        """Delete a profile and its associated credentials."""
        name = name.strip()
        data = self._load_config_raw()
        profiles = data.get("profiles", {})

        if name not in profiles:
            raise ProfileNotFoundError(f"Profile '{name}' does not exist.")

        default_profile = data.get("default_profile", "local")
        if name == default_profile:
            other_profiles = [p for p in profiles if p != name]
            if other_profiles:
                raise ProfileValidationError(
                    f"Cannot delete default profile '{name}'. "
                    f"Use 'trailytics profile use <name>' to select another default first."
                )
            else:
                # If it's the last profile, remove it and reset default_profile to 'local'
                data["default_profile"] = "local"

        del profiles[name]
        self._save_config_raw(data)

        # Remove credential if present
        self.delete_credential(name)

    # =========================================================================
    # Credentials (credentials.toml) Operations
    # =========================================================================

    def _load_credentials_raw(self) -> Dict[str, Any]:
        """Load raw credentials.toml data, enforcing 0600 permissions."""
        self._check_and_enforce_credentials_permissions()
        return load_toml_file(self.credentials_path)

    def _save_credentials_raw(self, data: Dict[str, Any]) -> None:
        """Save raw credentials.toml data with 0600 permissions."""
        content = dumps_toml(data)
        self._safe_write_file(self.credentials_path, content, mode=0o600)

    def get_credential(self, profile_name: str) -> Optional[str]:
        """Get stored API key for a profile, or None."""
        profile_name = profile_name.strip()
        data = self._load_credentials_raw()
        profiles = data.get("profiles", {})
        if isinstance(profiles, dict):
            p_data = profiles.get(profile_name, {})
            if isinstance(p_data, dict):
                val = p_data.get("api_key")
                if val:
                    return str(val)
        return None

    def set_credential(self, profile_name: str, api_key: str) -> None:
        """Store an API key for a profile with 0600 permissions."""
        profile_name = profile_name.strip()
        api_key = api_key.strip()
        if not api_key:
            return

        data = self._load_credentials_raw()
        profiles = data.setdefault("profiles", {})
        p_data = profiles.setdefault(profile_name, {})
        p_data["api_key"] = api_key

        self._save_credentials_raw(data)

    def delete_credential(self, profile_name: str) -> None:
        """Remove credentials for a profile if they exist."""
        profile_name = profile_name.strip()
        if not self.credentials_path.is_file():
            return

        data = self._load_credentials_raw()
        profiles = data.get("profiles", {})
        if profile_name in profiles:
            del profiles[profile_name]
            self._save_credentials_raw(data)

    def has_credential(self, profile_name: str) -> bool:
        """Check if an API key is configured for a profile."""
        return self.get_credential(profile_name) is not None
