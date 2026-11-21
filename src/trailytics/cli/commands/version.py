"""Version command for Trailytics CLI."""

from __future__ import annotations

import importlib.metadata
import click
import trailytics
from trailytics.cli.runner import find_repository_root, get_repository_metadata
from trailytics.exceptions import RepositoryNotFoundError


@click.command("version", help="Show Trailytics version information.")
def version_cmd() -> None:
    """Display Trailytics and underlying engine version metadata."""
    trailytics_version = trailytics.__version__

    repo_error = None
    try:
        repo_dir = find_repository_root()
    except RepositoryNotFoundError as e:
        repo_dir = None
        repo_error = str(e).split("\n")[0]

    if repo_dir is not None:
        metadata = get_repository_metadata(repo_dir)
        opik_version = metadata.get("OPIK_VERSION", "2.2.138")
        opik_commit = metadata.get("OPIK_COMMIT", "unknown")
    else:
        try:
            opik_version = importlib.metadata.version("opik")
        except importlib.metadata.PackageNotFoundError:
            opik_version = "unavailable (repository not located)"

        if repo_error:
            opik_commit = f"unavailable ({repo_error})"
        else:
            opik_commit = "unavailable (repository not located)"

    click.echo(f"{'Trailytics':<12}{trailytics_version}")
    click.echo(f"{'Opik Engine':<12}{opik_version}")
    click.echo(f"{'Commit':<12}{opik_commit}")
