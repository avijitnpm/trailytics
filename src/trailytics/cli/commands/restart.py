"""Restart command for Trailytics CLI."""

from __future__ import annotations

import click
from trailytics.cli.commands.start import run_start
from trailytics.cli.commands.stop import run_stop
from trailytics.cli.runner import is_development_mode
from trailytics.deployment.orchestrator import StandaloneOrchestrator


def run_restart() -> int:
    """Execute the Trailytics restart command in development or standalone mode.

    Returns:
        The exit code of the process (0 on success).
    """
    if is_development_mode():
        stop_code = run_stop()
        if stop_code != 0:
            click.echo("Trailytics: stopping deployment failed; aborting restart.", err=True)
            return stop_code
        return run_start()
    else:
        orchestrator = StandaloneOrchestrator()
        return orchestrator.restart()


@click.command("restart", help="Restart Trailytics deployment.")
def restart_cmd() -> None:
    """Restart Trailytics deployment by stopping and starting containers."""
    code = run_restart()
    if code != 0:
        raise click.exceptions.Exit(code)
