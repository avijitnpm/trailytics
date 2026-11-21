"""Trailytics configuration module.

Bridges Trailytics settings and environment variables to the underlying Opik engine,
defaulting to the local Trailytics backend and disabling upstream telemetry by default.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import opik.config
from opik.api_objects import opik_client

DEFAULT_TRAILYTICS_URL: str = "http://localhost:5173/api/"
DEFAULT_PROJECT_NAME: str = "Default Project"
DEFAULT_WORKSPACE: str = "default"

_CONFIG_INITIALIZED: bool = False


def get_trailytics_url() -> str:
    """Return the resolved Trailytics backend URL."""
    return (
        os.environ.get("TRAILYTICS_URL")
        or os.environ.get("OPIK_URL_OVERRIDE")
        or DEFAULT_TRAILYTICS_URL
    )


def get_trailytics_project() -> str:
    """Return the resolved Trailytics project name."""
    return (
        os.environ.get("TRAILYTICS_PROJECT")
        or os.environ.get("OPIK_PROJECT_NAME")
        or DEFAULT_PROJECT_NAME
    )


def get_trailytics_workspace() -> str:
    """Return the resolved Trailytics workspace name."""
    return (
        os.environ.get("TRAILYTICS_WORKSPACE")
        or os.environ.get("OPIK_WORKSPACE")
        or DEFAULT_WORKSPACE
    )


def get_trailytics_api_key() -> Optional[str]:
    """Return the resolved API key, if configured."""
    return os.environ.get("TRAILYTICS_API_KEY") or os.environ.get("OPIK_API_KEY")


def initialize_defaults() -> None:
    """Initialize Trailytics default configuration in the Opik runtime.

    Ensures that by default:
    1. Tracing targets the local Trailytics backend at http://localhost:5173/api/
    2. Upstream telemetry and external Sentry error reporting are disabled
    3. Trailytics environment variables are mapped to Opik configuration
    """
    global _CONFIG_INITIALIZED

    # Disable external analytics/telemetry to Comet unless explicitly requested
    if "OPIK_ANALYTICS_ENABLE" not in os.environ and "TRAILYTICS_ANALYTICS_ENABLE" not in os.environ:
        os.environ["OPIK_ANALYTICS_ENABLE"] = "false"
        opik.config.update_session_config("analytics_enable", False)

    # Disable external Sentry error tracking to Comet unless explicitly requested
    if "OPIK_SENTRY_ENABLE" not in os.environ and "TRAILYTICS_SENTRY_ENABLE" not in os.environ:
        os.environ["OPIK_SENTRY_ENABLE"] = "false"
        opik.config.update_session_config("sentry_enable", False)

    # Resolve URL, project, workspace
    url = get_trailytics_url()
    project = get_trailytics_project()
    workspace = get_trailytics_workspace()
    api_key = get_trailytics_api_key()

    # Mirror into environment variables for underlying libraries/tools
    os.environ.setdefault("OPIK_URL_OVERRIDE", url)
    os.environ.setdefault("OPIK_PROJECT_NAME", project)
    os.environ.setdefault("OPIK_WORKSPACE", workspace)
    if api_key:
        os.environ.setdefault("OPIK_API_KEY", api_key)

    # Update Opik session cache (source #2 in OpikConfig)
    opik.config.update_session_config("url_override", url)
    opik.config.update_session_config("project_name", project)
    opik.config.update_session_config("workspace", workspace)
    if api_key:
        opik.config.update_session_config("api_key", api_key)

    _CONFIG_INITIALIZED = True


def ensure_configured() -> None:
    """Ensure defaults have been applied."""
    if not _CONFIG_INITIALIZED:
        initialize_defaults()


def configure(
    url: Optional[str] = None,
    project_name: Optional[str] = None,
    workspace: Optional[str] = None,
    api_key: Optional[str] = None,
) -> None:
    """Configure the Trailytics runtime.

    Args:
        url: Backend URL (e.g. 'http://localhost:5173/api/').
        project_name: Default project name for traces.
        workspace: Workspace name (defaults to 'default').
        api_key: Optional API key.
    """
    ensure_configured()

    if url is not None:
        os.environ["TRAILYTICS_URL"] = url
        os.environ["OPIK_URL_OVERRIDE"] = url
        opik.config.update_session_config("url_override", url)

    if project_name is not None:
        os.environ["TRAILYTICS_PROJECT"] = project_name
        os.environ["OPIK_PROJECT_NAME"] = project_name
        opik.config.update_session_config("project_name", project_name)

    if workspace is not None:
        os.environ["TRAILYTICS_WORKSPACE"] = workspace
        os.environ["OPIK_WORKSPACE"] = workspace
        opik.config.update_session_config("workspace", workspace)

    if api_key is not None:
        os.environ["TRAILYTICS_API_KEY"] = api_key
        os.environ["OPIK_API_KEY"] = api_key
        opik.config.update_session_config("api_key", api_key)

    # Reset any cached global client so new configuration is picked up
    opik_client.reset_global_client(end_client=False)


def get_config() -> Dict[str, Any]:
    """Return current Trailytics configuration summary."""
    ensure_configured()
    return {
        "url": get_trailytics_url(),
        "project_name": get_trailytics_project(),
        "workspace": get_trailytics_workspace(),
        "api_key_configured": get_trailytics_api_key() is not None,
    }
