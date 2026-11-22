"""Start command for Trailytics CLI."""

from __future__ import annotations

import click
from trailytics.cli.runner import execute_lifecycle_script, is_development_mode
from trailytics.deployment.orchestrator import StandaloneOrchestrator


def run_start() -> int:
    """Execute the Trailytics start command in development or standalone mode.

    Returns:
        The exit code of the process (0 on success).
    """
    if is_development_mode():
        return execute_lifecycle_script("start.sh")
    else:
        orchestrator = StandaloneOrchestrator()
        return orchestrator.start()


@click.command("start", help="Start Trailytics deployment.")
def start_cmd() -> None:
    """Start Trailytics deployment and verify services."""
    code = run_start()
    if code != 0:
        raise click.exceptions.Exit(code)
