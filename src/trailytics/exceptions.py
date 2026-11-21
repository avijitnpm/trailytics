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
