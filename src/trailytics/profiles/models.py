"""Data models and validation for Trailytics connection profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from trailytics.exceptions import ProfileValidationError

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
RESERVED_NAMES = {"default_profile", "profiles"}
VALID_PROFILE_TYPES = {"local", "remote"}


@dataclass
class Profile:
    """Represents a named Trailytics deployment profile."""

    name: str
    type: str = "remote"
    url: str = "http://localhost:5173/api"
    workspace: str = "default"
    default_project: str = "Default Project"
    description: str = ""

    def validate(self) -> None:
        """Validate profile fields, raising ProfileValidationError if invalid."""
        # 1. Name validation
        if not self.name or not isinstance(self.name, str):
            raise ProfileValidationError("Profile name cannot be empty.")
        if len(self.name) > 64:
            raise ProfileValidationError(
                f"Profile name '{self.name}' exceeds maximum length of 64 characters."
            )
        if not _NAME_PATTERN.match(self.name):
            raise ProfileValidationError(
                f"Invalid profile name '{self.name}'. "
                "Profile names may only contain letters, numbers, hyphens (-), and underscores (_)."
            )
        if self.name.lower() in RESERVED_NAMES:
            raise ProfileValidationError(
                f"Profile name '{self.name}' is reserved and cannot be used."
            )

        # 2. Type validation
        normalized_type = str(self.type).strip().lower()
        if normalized_type not in VALID_PROFILE_TYPES:
            raise ProfileValidationError(
                f"Invalid profile type '{self.type}'. Must be 'local' or 'remote'."
            )
        self.type = normalized_type

        # 3. URL validation
        if not self.url or not isinstance(self.url, str):
            raise ProfileValidationError("Profile URL cannot be empty.")
        parsed = urlparse(self.url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ProfileValidationError(
                f"Invalid URL '{self.url}'. URL must begin with 'http://' or 'https://'."
            )
        if not parsed.netloc:
            raise ProfileValidationError(
                f"Invalid URL '{self.url}'. URL must include a host/domain name."
            )
        self.url = self.url.strip()

        # 4. Workspace & Project
        if not self.workspace or not isinstance(self.workspace, str):
            self.workspace = "default"
        else:
            self.workspace = self.workspace.strip()

        if not self.default_project or not isinstance(self.default_project, str):
            self.default_project = "Default Project"
        else:
            self.default_project = self.default_project.strip()

        if self.description is None:
            self.description = ""
        else:
            self.description = str(self.description).strip()

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to configuration dictionary."""
        return {
            "type": self.type,
            "url": self.url,
            "workspace": self.workspace,
            "default_project": self.default_project,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> Profile:
        """Create and validate a Profile from configuration dictionary."""
        profile = cls(
            name=name,
            type=str(data.get("type", "remote")).strip().lower(),
            url=str(data.get("url", "http://localhost:5173/api")),
            workspace=str(data.get("workspace", "default")),
            default_project=str(data.get("default_project", "Default Project")),
            description=str(data.get("description", "")),
        )
        profile.validate()
        return profile


@dataclass
class ResolvedConfig:
    """Resolved Trailytics configuration after applying precedence hierarchy."""

    profile_name: str
    type: str
    url: str
    workspace: str
    project: str
    api_key: Optional[str] = None
    has_api_key: bool = False
    sources: Dict[str, str] = field(default_factory=dict)
