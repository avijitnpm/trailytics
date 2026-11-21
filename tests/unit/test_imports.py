"""Tests for Trailytics public API imports and exports."""

import trailytics
from trailytics import (
    Client,
    Trailytics,
    configure,
    context,
    flush,
    flush_tracker,
    get_config,
    track,
    RepositoryNotFoundError,
    ScriptExecutionError,
    TrailyticsConfigurationError,
    TrailyticsError,
    __version__,
)


def test_package_version():
    assert __version__ == "0.3.0"
    assert trailytics.__version__ == "0.3.0"


def test_public_symbols_exported():
    expected_symbols = [
        "__version__",
        "track",
        "configure",
        "flush",
        "flush_tracker",
        "Client",
        "Trailytics",
        "context",
        "get_config",
        "TrailyticsError",
        "TrailyticsConfigurationError",
        "RepositoryNotFoundError",
        "ScriptExecutionError",
    ]
    for symbol in expected_symbols:
        assert hasattr(trailytics, symbol), f"Symbol '{symbol}' not found in trailytics"


def test_client_alias():
    assert Client is Trailytics
    assert trailytics.Client is trailytics.Trailytics


def test_flush_alias():
    assert flush is flush_tracker
    assert trailytics.flush is trailytics.flush_tracker


def test_context_exports():
    assert hasattr(context, "get_current_trace_data")
    assert hasattr(context, "get_current_span_data")
    assert hasattr(context, "update_current_trace")
    assert hasattr(context, "update_current_span")
    assert hasattr(context, "get_distributed_trace_headers")
