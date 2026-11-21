"""Trailytics function instrumentation and tracking decorators.

Provides the @track decorator and flush helpers that delegate to the underlying Opik engine.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Dict, List, Optional, Union

import opik
import opik.types
from opik.api_objects import opik_client

from .config import ensure_configured


def track(
    name: Optional[Union[Callable[..., Any], str]] = None,
    type: opik.types.SpanType = "general",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    capture_input: bool = True,
    ignore_arguments: Optional[List[str]] = None,
    capture_output: bool = True,
    generations_aggregator: Optional[Callable[[List[Any]], Any]] = None,
    flush: bool = False,
    project_name: Optional[str] = None,
    create_duplicate_root_span: bool = True,
    entrypoint: bool = False,
    source: Optional[opik.types.TraceSource] = None,
    environment: Optional[str] = None,
) -> Any:
    """Trailytics tracking decorator to trace function execution.

    Can be used bare or with parameters:
        @trailytics.track
        def generate(prompt): ...

        @trailytics.track(name="custom_name", tags=["v1"])
        def generate(prompt): ...

    Supports synchronous functions, asynchronous functions, and generator functions.
    Preserves signature, docstrings, and exception behavior.
    """
    ensure_configured()

    return opik.track(
        name=name,
        type=type,
        tags=tags,
        metadata=metadata,
        capture_input=capture_input,
        ignore_arguments=ignore_arguments,
        capture_output=capture_output,
        generations_aggregator=generations_aggregator,
        flush=flush,
        project_name=project_name,
        create_duplicate_root_span=create_duplicate_root_span,
        entrypoint=entrypoint,
        source=source,
        environment=environment,
    )


def flush(timeout: Optional[int] = None) -> bool:
    """Flush pending messages and traces to the Trailytics backend.

    Args:
        timeout: Maximum seconds to wait. None waits for default flush timeout.

    Returns:
        True if all messages were delivered successfully, False otherwise.
    """
    ensure_configured()
    client = opik_client.get_global_client()
    return client.flush(timeout=timeout)


flush_tracker = flush
