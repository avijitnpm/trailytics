"""Main CLI entry point for Trailytics."""

from __future__ import annotations

import click
import trailytics
from trailytics.cli.commands.version import version_cmd

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=False,
)
@click.version_option(
    trailytics.__version__,
    "-v",
    "--version",
    prog_name="trailytics",
    message="%(prog)s %(version)s",
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Trailytics - AI Observability & Tracing CLI."""
    ctx.ensure_object(dict)


# Register subcommands
cli.add_command(version_cmd)


if __name__ == "__main__":
    cli()
