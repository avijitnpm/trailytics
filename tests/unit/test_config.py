"""Tests for Trailytics configuration, environment variable resolution, and Opik translation."""

import os
from unittest import mock

import opik.config
import trailytics
from trailytics.config import (
    DEFAULT_PROJECT_NAME,
    DEFAULT_TRAILYTICS_URL,
    DEFAULT_WORKSPACE,
    configure,
    ensure_configured,
    get_config,
    get_trailytics_api_key,
    get_trailytics_project,
    get_trailytics_url,
    get_trailytics_workspace,
    initialize_defaults,
)


def test_default_config_values():
    initialize_defaults()
    assert get_trailytics_url() == DEFAULT_TRAILYTICS_URL
    assert DEFAULT_TRAILYTICS_URL == "http://localhost:5173/api/"
    assert get_trailytics_project() == DEFAULT_PROJECT_NAME
    assert DEFAULT_PROJECT_NAME == "Default Project"
    assert get_trailytics_workspace() == DEFAULT_WORKSPACE
    assert DEFAULT_WORKSPACE == "default"
    assert get_trailytics_api_key() is None


def test_environment_variable_override_trailytics_prefix():
    with mock.patch.dict(
        os.environ,
        {
            "TRAILYTICS_URL": "http://custom-host:8000/api/",
            "TRAILYTICS_PROJECT": "custom-project",
            "TRAILYTICS_WORKSPACE": "custom-ws",
            "TRAILYTICS_API_KEY": "custom-key",
        },
    ):
        assert get_trailytics_url() == "http://custom-host:8000/api/"
        assert get_trailytics_project() == "custom-project"
        assert get_trailytics_workspace() == "custom-ws"
        assert get_trailytics_api_key() == "custom-key"


def test_environment_variable_fallback_opik_prefix():
    with mock.patch.dict(
        os.environ,
        {
            "OPIK_URL_OVERRIDE": "http://opik-host:8000/api/",
            "OPIK_PROJECT_NAME": "opik-project",
            "OPIK_WORKSPACE": "opik-ws",
            "OPIK_API_KEY": "opik-key",
        },
    ):
        assert get_trailytics_url() == "http://opik-host:8000/api/"
        assert get_trailytics_project() == "opik-project"
        assert get_trailytics_workspace() == "opik-ws"
        assert get_trailytics_api_key() == "opik-key"


def test_configure_updates_settings_and_environment():
    configure(
        url="http://new-trailytics:5173/api/",
        project_name="Phase2-Test",
        workspace="dev",
        api_key="secret-key",
    )

    cfg = get_config()
    assert cfg["url"] == "http://new-trailytics:5173/api/"
    assert cfg["project_name"] == "Phase2-Test"
    assert cfg["workspace"] == "dev"
    assert cfg["api_key_configured"] is True

    # Verify mirrored in environment
    assert os.environ.get("TRAILYTICS_URL") == "http://new-trailytics:5173/api/"
    assert os.environ.get("OPIK_URL_OVERRIDE") == "http://new-trailytics:5173/api/"
    assert os.environ.get("TRAILYTICS_PROJECT") == "Phase2-Test"
    assert os.environ.get("OPIK_PROJECT_NAME") == "Phase2-Test"


def test_telemetry_disabled_by_default():
    initialize_defaults()
    # External analytics and sentry must be disabled by default
    assert os.environ.get("OPIK_ANALYTICS_ENABLE") == "false"
    assert os.environ.get("OPIK_SENTRY_ENABLE") == "false"
