"""Trailytics - AI Observability & Tracing.

Product-facing layer built on the Opik tracing engine.
"""

from .config import configure, get_config, initialize_defaults
from .client import Client
from .tracker import flush, flush_tracker, track
from .exceptions import TrailyticsConfigurationError, TrailyticsError
from . import context

# Automatically initialize Trailytics local defaults upon package import
initialize_defaults()

Trailytics = Client

__version__ = "0.2.0"

__all__ = [
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
]
