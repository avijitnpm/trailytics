"""Logs command for Trailytics CLI."""

from __future__ import annotations

from typing import List, Optional, Tuple
import click
from trailytics.cli.runner import execute_lifecycle_script, is_development_mode
from trailytics.deployment.orchestrator import StandaloneOrchestrator


def run_logs(args: List[str]) -> int:
    """Execute the logs command in development or standalone mode."""
    if is_development_mode():
        return execute_lifecycle_script("logs.sh", args=args, allow_interrupt=True)
    else:
        orchestrator = StandaloneOrchestrator()
        return orchestrator.logs(args)


def build_logs_args(
    follow: bool = False,
    tail: Optional[str] = "100",
    since: Optional[str] = None,
    timestamps: bool = False,
    services: Tuple[str, ...] = (),
) -> List[str]:
    """Validate inputs and construct argument list for logs.sh."""
    args: List[str] = []

    if follow:
        args.append("-f")

    if tail is not None:
        tail_str = str(tail).strip()
        if tail_str.lower() != "all" and not tail_str.isdigit():
            raise click.BadParameter(
                f"Invalid tail value '{tail}'. Must be a non-negative integer or 'all'.",
                param_hint="'--tail'",
            )
        args.extend(["--tail", tail_str])

    if since is not None:
        since_str = str(since).strip()
        if not since_str:
            raise click.BadParameter(
                "Duration cannot be empty.",
                param_hint="'--since'",
            )
        args.extend(["--since", since_str])

    if timestamps:
        args.append("--timestamps")

    if services:
        args.extend(services)

    return args


@click.command("logs", help="View logs from deployment containers.")
@click.option("-f", "--follow", is_flag=True, default=False, help="Follow log output continuously.")
@click.option(
    "--tail",
    default="100",
    help="Number of lines to show from the end of the logs (default: 100, or 'all').",
)
@click.option(
    "--since",
    default=None,
    help="Show logs since timestamp or relative duration (e.g. 10m, 1h).",
)
@click.option(
    "-t",
    "--timestamps",
    is_flag=True,
    default=False,
    help="Show timestamps in log output.",
)
@click.argument("services", nargs=-1)
def logs_cmd(
    follow: bool,
    tail: Optional[str],
    since: Optional[str],
    timestamps: bool,
    services: Tuple[str, ...],
) -> None:
    """View and follow logs from Trailytics deployment containers."""
    args = build_logs_args(
        follow=follow,
        tail=tail,
        since=since,
        timestamps=timestamps,
        services=services,
    )
    code = run_logs(args)
    if code != 0:
        raise click.exceptions.Exit(code)
