"""Tests for Trailytics @track decorator and flush operations."""

import asyncio
from unittest import mock
import pytest

import trailytics
from trailytics import flush, track
from opik.api_objects import opik_client


def test_track_bare_decorator_sync():
    """Verify @trailytics.track bare decorator preserves function execution and return value."""
    @trailytics.track
    def add(a: int, b: int) -> int:
        return a + b

    result = add(2, 3)
    assert result == 5
    assert add.__name__ == "add"


def test_track_from_import_style():
    """Verify 'from trailytics import track' uses identical implementation."""
    @track
    def multiply(a: int, b: int) -> int:
        return a * b

    assert multiply(3, 4) == 12
    assert multiply.__name__ == "multiply"


def test_track_with_parameters():
    """Verify @track with explicit options (name, tags, metadata, project_name)."""
    @trailytics.track(
        name="custom_computation",
        tags=["math", "v1"],
        metadata={"priority": "high"},
        project_name="CustomProject",
    )
    def compute(val: str) -> str:
        return f"computed_{val}"

    result = compute("test")
    assert result == "computed_test"


def test_track_async_function():
    """Verify @track works transparently on async functions."""
    @trailytics.track
    async def async_fetch(url: str) -> dict:
        await asyncio.sleep(0.01)
        return {"url": url, "data": "ok"}

    result = asyncio.run(async_fetch("http://example.com"))
    assert result == {"url": "http://example.com", "data": "ok"}


def test_track_generator_function():
    """Verify @track works transparently on generator functions."""
    @trailytics.track
    def count_up(n: int):
        for i in range(n):
            yield i

    results = list(count_up(3))
    assert results == [0, 1, 2]


def test_track_nested_functions():
    """Verify nested tracked functions execute and return properly."""
    @trailytics.track
    def inner(x: int) -> int:
        return x * 2

    @trailytics.track
    def outer(x: int) -> int:
        return inner(x) + 1

    assert outer(5) == 11


def test_track_error_propagation():
    """Verify exceptions in user functions propagate cleanly to caller."""
    class CustomWorkflowError(Exception):
        pass

    @trailytics.track
    def failing_function():
        raise CustomWorkflowError("Operation failed")

    with pytest.raises(CustomWorkflowError) as exc_info:
        failing_function()

    assert "Operation failed" in str(exc_info.value)


def test_track_client_error_resilience():
    """Verify that an unexpected error inside tracing infrastructure does not break user function."""
    mock_client = mock.MagicMock()
    mock_client.span.side_effect = RuntimeError("SDK transport failure")
    mock_client.trace.side_effect = RuntimeError("SDK transport failure")

    with mock.patch.object(opik_client, "get_global_client", return_value=mock_client):
        @trailytics.track
        def safe_function(x: int) -> int:
            return x * 10

        # User's function must still execute successfully and return its result
        assert safe_function(4) == 40


def test_flush_delegation():
    """Verify flush delegates to underlying client."""
    mock_client = mock.MagicMock()
    mock_client.flush.return_value = True

    with mock.patch.object(opik_client, "get_global_client", return_value=mock_client):
        result = flush(timeout=5)
        assert result is True
        mock_client.flush.assert_called_once_with(timeout=5)
