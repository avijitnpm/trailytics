"""Configuration resolver applying Trailytics precedence rules."""

from __future__ import annotations

import os
from typing import Optional

from trailytics.exceptions import ProfileNotFoundError
from trailytics.profiles.models import Profile, ResolvedConfig
from trailytics.profiles.storage import ProfileStorage

BUILTIN_LOCAL_PROFILE = Profile(
    name="local",
    type="local",
    url="http://localhost:5173/api",
    workspace="default",
    default_project="Default Project",
    description="Built-in local Trailytics deployment",
)


class ConfigResolver:
    """Resolves Trailytics configuration across CLI, environment, profile, and defaults."""

    def __init__(self, storage: Optional[ProfileStorage] = None) -> None:
        self.storage = storage or ProfileStorage()

    def resolve(
        self,
        cli_profile: Optional[str] = None,
        cli_url: Optional[str] = None,
        cli_workspace: Optional[str] = None,
        cli_project: Optional[str] = None,
        cli_api_key: Optional[str] = None,
    ) -> ResolvedConfig:
        """Resolve full configuration based on strict precedence rules."""
        sources: dict[str, str] = {}

        # ---------------------------------------------------------------------
        # 1. Profile Resolution
        # Precedence: CLI --profile > TRAILYTICS_PROFILE > default_profile > 'local'
        # ---------------------------------------------------------------------
        profile_name = "local"
        if cli_profile:
            profile_name = cli_profile.strip()
            sources["profile_name"] = "cli"
        elif "TRAILYTICS_PROFILE" in os.environ and os.environ["TRAILYTICS_PROFILE"].strip():
            profile_name = os.environ["TRAILYTICS_PROFILE"].strip()
            sources["profile_name"] = "environment"
        else:
            default_name = self.storage.get_default_profile_name()
            if default_name:
                profile_name = default_name
                sources["profile_name"] = "config_default"
            else:
                profile_name = "local"
                sources["profile_name"] = "builtin_default"

        # Load profile definition
        configured_profile = self.storage.get_profile(profile_name)
        if configured_profile is None:
            if profile_name == "local":
                # Fall back to built-in local profile
                profile = BUILTIN_LOCAL_PROFILE
            else:
                raise ProfileNotFoundError(
                    f"Profile '{profile_name}' does not exist. "
                    "Use 'trailytics profile list' to see available profiles "
                    f"or 'trailytics profile create {profile_name}' to create it."
                )
        else:
            profile = configured_profile

        profile_type = profile.type

        # ---------------------------------------------------------------------
        # 2. URL Resolution
        # Precedence: CLI > TRAILYTICS_URL > OPIK_URL_OVERRIDE > profile.url > default
        # ---------------------------------------------------------------------
        if cli_url and cli_url.strip():
            url = cli_url.strip()
            sources["url"] = "cli"
        elif "TRAILYTICS_URL" in os.environ and os.environ["TRAILYTICS_URL"].strip():
            url = os.environ["TRAILYTICS_URL"].strip()
            sources["url"] = "environment:TRAILYTICS_URL"
        elif "OPIK_URL_OVERRIDE" in os.environ and os.environ["OPIK_URL_OVERRIDE"].strip():
            url = os.environ["OPIK_URL_OVERRIDE"].strip()
            sources["url"] = "environment:OPIK_URL_OVERRIDE"
        elif profile.url:
            url = profile.url
            sources["url"] = "profile"
        else:
            url = "http://localhost:5173/api"
            sources["url"] = "default"

        # ---------------------------------------------------------------------
        # 3. Workspace Resolution
        # Precedence: CLI > TRAILYTICS_WORKSPACE > OPIK_WORKSPACE > profile.workspace > default
        # ---------------------------------------------------------------------
        if cli_workspace and cli_workspace.strip():
            workspace = cli_workspace.strip()
            sources["workspace"] = "cli"
        elif "TRAILYTICS_WORKSPACE" in os.environ and os.environ["TRAILYTICS_WORKSPACE"].strip():
            workspace = os.environ["TRAILYTICS_WORKSPACE"].strip()
            sources["workspace"] = "environment:TRAILYTICS_WORKSPACE"
        elif "OPIK_WORKSPACE" in os.environ and os.environ["OPIK_WORKSPACE"].strip():
            workspace = os.environ["OPIK_WORKSPACE"].strip()
            sources["workspace"] = "environment:OPIK_WORKSPACE"
        elif profile.workspace:
            workspace = profile.workspace
            sources["workspace"] = "profile"
        else:
            workspace = "default"
            sources["workspace"] = "default"

        # ---------------------------------------------------------------------
        # 4. Project Resolution
        # Precedence: CLI > TRAILYTICS_PROJECT > OPIK_PROJECT_NAME > profile.default_project > default
        # ---------------------------------------------------------------------
        if cli_project and cli_project.strip():
            project = cli_project.strip()
            sources["project"] = "cli"
        elif "TRAILYTICS_PROJECT" in os.environ and os.environ["TRAILYTICS_PROJECT"].strip():
            project = os.environ["TRAILYTICS_PROJECT"].strip()
            sources["project"] = "environment:TRAILYTICS_PROJECT"
        elif "OPIK_PROJECT_NAME" in os.environ and os.environ["OPIK_PROJECT_NAME"].strip():
            project = os.environ["OPIK_PROJECT_NAME"].strip()
            sources["project"] = "environment:OPIK_PROJECT_NAME"
        elif profile.default_project:
            project = profile.default_project
            sources["project"] = "profile"
        else:
            project = "Default Project"
            sources["project"] = "default"

        # ---------------------------------------------------------------------
        # 5. API Key Resolution
        # Precedence: CLI > TRAILYTICS_API_KEY > OPIK_API_KEY > credentials.toml > None
        # ---------------------------------------------------------------------
        api_key: Optional[str] = None
        if cli_api_key and cli_api_key.strip():
            api_key = cli_api_key.strip()
            sources["api_key"] = "cli"
        elif "TRAILYTICS_API_KEY" in os.environ and os.environ["TRAILYTICS_API_KEY"].strip():
            api_key = os.environ["TRAILYTICS_API_KEY"].strip()
            sources["api_key"] = "environment:TRAILYTICS_API_KEY"
        elif "OPIK_API_KEY" in os.environ and os.environ["OPIK_API_KEY"].strip():
            api_key = os.environ["OPIK_API_KEY"].strip()
            sources["api_key"] = "environment:OPIK_API_KEY"
        else:
            stored_key = self.storage.get_credential(profile_name)
            if stored_key:
                api_key = stored_key
                sources["api_key"] = "credentials"
            else:
                sources["api_key"] = "none"

        return ResolvedConfig(
            profile_name=profile_name,
            type=profile_type,
            url=url,
            workspace=workspace,
            project=project,
            api_key=api_key,
            has_api_key=api_key is not None,
            sources=sources,
        )


def resolve_config(
    cli_profile: Optional[str] = None,
    cli_url: Optional[str] = None,
    cli_workspace: Optional[str] = None,
    cli_project: Optional[str] = None,
    cli_api_key: Optional[str] = None,
    storage: Optional[ProfileStorage] = None,
) -> ResolvedConfig:
    """Convenience helper to resolve configuration."""
    resolver = ConfigResolver(storage=storage)
    return resolver.resolve(
        cli_profile=cli_profile,
        cli_url=cli_url,
        cli_workspace=cli_workspace,
        cli_project=cli_project,
        cli_api_key=cli_api_key,
    )
