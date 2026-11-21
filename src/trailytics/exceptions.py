"""Trailytics exceptions.

Provides Trailytics error types while preserving access to underlying Opik exceptions.
"""

from typing import Any


class TrailyticsError(Exception):
    """Base exception for all Trailytics errors."""

    pass


class TrailyticsConfigurationError(TrailyticsError):
    """Raised when Trailytics configuration is invalid or missing."""

    pass


class RepositoryNotFoundError(TrailyticsError):
    """Raised when the Trailytics repository root cannot be located or is invalid."""

    pass


class ScriptExecutionError(TrailyticsError):
    """Raised when a lifecycle script execution fails or returns a non-zero exit code."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code
