"""Trailytics client implementation.

Thin delegation layer around the underlying Opik client, configuring Trailytics defaults.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import opik
from opik.api_objects import opik_client

from .config import (
    ensure_configured,
    get_trailytics_api_key,
    get_trailytics_project,
    get_trailytics_url,
    get_trailytics_workspace,
)


class Client:
    """Trailytics Client for interacting with the Trailytics tracing engine.

    Wraps the underlying Opik client, automatically applying Trailytics
    configuration, local endpoints, and privacy defaults.
    """

    def __init__(
        self,
        project_name: Optional[str] = None,
        workspace: Optional[str] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        batching: bool = True,
        **kwargs: Any,
    ) -> None:
        ensure_configured()
        resolved_url = url or get_trailytics_url()
        resolved_project = project_name or get_trailytics_project()
        resolved_workspace = workspace or get_trailytics_workspace()
        resolved_api_key = api_key or get_trailytics_api_key()

        self._opik_client = opik.Opik(
            project_name=resolved_project,
            workspace=resolved_workspace,
            host=resolved_url,
            api_key=resolved_api_key,
            batching=batching,
            **kwargs,
        )

    @property
    def opik_client(self) -> opik.Opik:
        """Access the underlying Opik client instance."""
        return self._opik_client

    @property
    def project_name(self) -> str:
        """Return the active project name."""
        return self._opik_client.project_name

    def trace(self, *args: Any, **kwargs: Any) -> Any:
        """Create and log a trace manually."""
        return self._opik_client.trace(*args, **kwargs)

    def span(self, *args: Any, **kwargs: Any) -> Any:
        """Create and log a span manually."""
        return self._opik_client.span(*args, **kwargs)

    def flush(self, timeout: Optional[int] = None) -> bool:
        """Flush queued traces and spans to the Trailytics backend."""
        return self._opik_client.flush(timeout=timeout)

    def end(self, timeout: Optional[int] = None, *, flush: bool = True) -> Any:
        """End client session and release transport connections."""
        return self._opik_client.end(timeout=timeout, flush=flush)

    def get_trace_content(self, id: str) -> Any:
        """Retrieve trace content from the backend by trace ID."""
        return self._opik_client.get_trace_content(id=id)

    def get_project(self, project_id: str) -> Any:
        """Retrieve project information by project ID."""
        return self._opik_client.get_project(project_id)

    def search_traces(self, *args: Any, **kwargs: Any) -> Any:
        """Search traces with filters."""
        return self._opik_client.search_traces(*args, **kwargs)

    def search_spans(self, *args: Any, **kwargs: Any) -> Any:
        """Search spans with filters."""
        return self._opik_client.search_spans(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Forward any other attribute or method call directly to the Opik client."""
        return getattr(self._opik_client, name)
