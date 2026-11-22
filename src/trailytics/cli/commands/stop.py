"""Stop command for Trailytics CLI."""

from __future__ import annotations

import click
from trailytics.cli.runner import execute_lifecycle_script, is_development_mode
from trailytics.deployment.orchestrator import StandaloneOrchestrator


def run_stop() -> int:
    """Execute the Trailytics stop command in development or standalone mode.

    Returns:
        The exit code of the process (0 on success).
    """
    if is_development_mode():
        return execute_lifecycle_script("stop.sh")
    else:
        orchestrator = StandaloneOrchestrator()
        return orchestrator.stop()


@click.command("stop", help="Stop Trailytics deployment without removing persistent data.")
def stop_cmd() -> None:
    """Stop Trailytics deployment without removing persistent data."""
    code = run_stop()
    if code != 0:
        raise click.exceptions.Exit(code)
