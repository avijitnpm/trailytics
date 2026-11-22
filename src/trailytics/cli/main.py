"""Main CLI entry point for Trailytics."""

from __future__ import annotations

import click
import trailytics
from trailytics.cli.commands.doctor import doctor_cmd
from trailytics.cli.commands.logs import logs_cmd
from trailytics.cli.commands.profile import profile_group
from trailytics.cli.commands.restart import restart_cmd
from trailytics.cli.commands.start import start_cmd
from trailytics.cli.commands.status import status_cmd
from trailytics.cli.commands.stop import stop_cmd
from trailytics.cli.commands.version import version_cmd

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=False,
)
@click.option(
    "--profile",
    "-p",
    "profile",
    default=None,
    help="Name of connection profile to use.",
)
@click.version_option(
    trailytics.__version__,
    "-v",
    "--version",
    prog_name="trailytics",
    message="%(prog)s %(version)s",
)
@click.pass_context
def cli(ctx: click.Context, profile: str | None = None) -> None:
    """Trailytics - AI Observability & Tracing CLI."""
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile


# Register subcommands
cli.add_command(profile_group)
cli.add_command(start_cmd)
cli.add_command(stop_cmd)
cli.add_command(restart_cmd)
cli.add_command(status_cmd)
cli.add_command(logs_cmd)
cli.add_command(doctor_cmd)
cli.add_command(version_cmd)


if __name__ == "__main__":
    cli()
