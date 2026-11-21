"""Unit test fixtures and configuration."""

import os
import pytest
from unittest import mock

import opik.config
from opik.api_objects import opik_client


@pytest.fixture(autouse=True)
def reset_environment_and_config():
    """Reset environment variables and Opik session config before each test."""
    original_env = os.environ.copy()

    # Clear any Trailytics and Opik environment variables
    for key in list(os.environ.keys()):
        if key.startswith("TRAILYTICS_") or key.startswith("OPIK_"):
            del os.environ[key]

    # Reset Opik global client
    opik_client.reset_global_client(end_client=False)

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
    opik_client.reset_global_client(end_client=False)
