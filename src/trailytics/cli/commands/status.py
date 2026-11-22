"""Status command for Trailytics CLI."""

from __future__ import annotations

import click
from trailytics.cli.runner import execute_lifecycle_script, is_development_mode
from trailytics.deployment.orchestrator import StandaloneOrchestrator


def run_status() -> int:
    """Execute the Trailytics status command in development or standalone mode.

    Returns:
        The exit code of the process (0 on success).
    """
    if is_development_mode():
        return execute_lifecycle_script("status.sh")
    else:
        orchestrator = StandaloneOrchestrator()
        return orchestrator.status()


@click.command("status", help="Show Trailytics deployment status.")
def status_cmd() -> None:
    """Display the health and runtime status of Trailytics containers."""
    code = run_status()
    if code != 0:
        raise click.exceptions.Exit(code)
