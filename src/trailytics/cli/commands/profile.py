"""Profile management commands for Trailytics CLI."""

from __future__ import annotations

import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from trailytics.exceptions import (
    ProfileAlreadyExistsError,
    ProfileNotFoundError,
    ProfileStorageError,
    ProfileValidationError,
)
from trailytics.profiles.models import Profile
from trailytics.profiles.storage import ProfileStorage

console = Console(highlight=False)


@click.group("profile", help="Manage Trailytics connection profiles.")
def profile_group() -> None:
    """Manage named connection profiles and credentials."""
    pass


@profile_group.command("list", help="List all configured connection profiles.")
@click.pass_context
def list_profiles_cmd(ctx: click.Context) -> None:
    """List all configured profiles, their types, endpoints, and default status."""
    storage = ProfileStorage()
    profiles = storage.list_profiles()
    default_profile_name = storage.get_default_profile_name()

    if not profiles:
        click.echo("No profiles configured.")
        click.echo("Using built-in default profile 'local' (http://localhost:5173/api).")
        click.echo("Run 'trailytics profile create <NAME>' to create a named profile.")
        return

    table = Table(title="Trailytics Connection Profiles", show_lines=False)
    table.add_column("Default", justify="center", style="bold green")
    table.add_column("Name", style="bold cyan")
    table.add_column("Type", style="magenta")
    table.add_column("URL")
    table.add_column("Workspace")
    table.add_column("API Key", justify="center")

    for name, p in sorted(profiles.items()):
        is_default = "*" if name == default_profile_name else ""
        has_key = "Yes" if storage.has_credential(name) else "No"
        table.add_row(
            is_default,
            name,
            p.type,
            p.url,
            p.workspace,
            has_key,
        )

    console.print(table)


@profile_group.command("create", help="Create a new connection profile.")
@click.argument("name")
@click.option(
    "--type",
    "-t",
    "profile_type",
    type=click.Choice(["local", "remote"], case_sensitive=False),
    default="remote",
    help="Profile deployment type (local or remote).",
)
@click.option(
    "--url",
    "-u",
    "url",
    default=None,
    help="Trailytics backend URL (e.g., https://trailytics.company.com/api).",
)
@click.option(
    "--workspace",
    "-w",
    "workspace",
    default="default",
    help="Target workspace name.",
)
@click.option(
    "--project",
    "-p",
    "project",
    default="Default Project",
    help="Default project name for tracing.",
)
@click.option(
    "--description",
    "-d",
    "description",
    default="",
    help="Human-readable description for the profile.",
)
@click.option(
    "--no-api-key",
    is_flag=True,
    default=False,
    help="Skip API key entry prompt.",
)
@click.option(
    "--set-default",
    is_flag=True,
    default=False,
    help="Set this profile as the default immediately.",
)
@click.pass_context
def create_profile_cmd(
    ctx: click.Context,
    name: str,
    profile_type: str,
    url: Optional[str],
    workspace: str,
    project: str,
    description: str,
    no_api_key: bool,
    set_default: bool,
) -> None:
    """Create a new Trailytics profile with specified endpoint settings."""
    storage = ProfileStorage()

    # Determine default URL based on type if not explicitly passed
    if not url:
        if profile_type.lower() == "local":
            url = "http://localhost:5173/api"
        else:
            url = "http://localhost:5173/api"

    profile = Profile(
        name=name,
        type=profile_type,
        url=url,
        workspace=workspace,
        default_project=project,
        description=description,
    )

    try:
        profile.validate()
    except ProfileValidationError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.exceptions.Exit(1)

    # Securely collect API key if not explicitly skipped
    api_key: Optional[str] = None
    if not no_api_key:
        try:
            prompt_val = click.prompt(
                "API Key (leave blank to skip)",
                default="",
                hide_input=True,
                show_default=False,
            )
            if prompt_val and prompt_val.strip():
                api_key = prompt_val.strip()
        except (click.Abort, EOFError):
            api_key = None

    try:
        storage.create_profile(profile, api_key=api_key, set_default=set_default)
    except ProfileAlreadyExistsError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.exceptions.Exit(1)
    except ProfileStorageError as e:
        click.echo(f"Error: Storage failure: {e}", err=True)
        raise click.exceptions.Exit(1)

    click.echo(f"Profile '{name}' created successfully.")


@profile_group.command("show", help="Show configuration details for a profile.")
@click.argument("name")
@click.pass_context
def show_profile_cmd(ctx: click.Context, name: str) -> None:
    """Display the configuration and credential status of a named profile."""
    storage = ProfileStorage()
    profile = storage.get_profile(name)

    if profile is None:
        if name == "local":
            from trailytics.profiles.resolver import BUILTIN_LOCAL_PROFILE

            profile = BUILTIN_LOCAL_PROFILE
        else:
            click.echo(f"Error: Profile '{name}' does not exist.", err=True)
            raise click.exceptions.Exit(1)

    default_name = storage.get_default_profile_name()
    is_default = "Yes" if profile.name == default_name else "No"
    has_api_key = "Yes" if storage.has_credential(profile.name) else "No"

    click.echo(f"{'Profile:':<18} {profile.name}")
    click.echo(f"{'Default Profile:':<18} {is_default}")
    click.echo(f"{'Type:':<18} {profile.type}")
    click.echo(f"{'URL:':<18} {profile.url}")
    click.echo(f"{'Workspace:':<18} {profile.workspace}")
    click.echo(f"{'Default Project:':<18} {profile.default_project}")
    click.echo(f"{'Description:':<18} {profile.description or '(none)'}")
    click.echo(f"{'API Key:':<18} {'Configured' if has_api_key == 'Yes' else 'Not configured'}")


@profile_group.command("use", help="Set a profile as the default.")
@click.argument("name")
@click.pass_context
def use_profile_cmd(ctx: click.Context, name: str) -> None:
    """Set the specified profile as the persistent default profile."""
    storage = ProfileStorage()
    try:
        storage.set_default_profile_name(name)
    except ProfileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.exceptions.Exit(1)
    except ProfileStorageError as e:
        click.echo(f"Error: Storage failure: {e}", err=True)
        raise click.exceptions.Exit(1)

    click.echo(f"Default profile set to '{name}'.")


@profile_group.command("delete", help="Delete a connection profile.")
@click.argument("name")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt.",
)
@click.pass_context
def delete_profile_cmd(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete a named profile and its stored credentials."""
    storage = ProfileStorage()

    # Pre-check existence before asking confirmation
    if storage.get_profile(name) is None:
        click.echo(f"Error: Profile '{name}' does not exist.", err=True)
        raise click.exceptions.Exit(1)

    # Pre-check default status
    default_name = storage.get_default_profile_name()
    if name == default_name:
        other_profiles = [p for p in storage.list_profiles() if p != name]
        if other_profiles:
            click.echo(
                f"Error: Cannot delete the default profile '{name}'. "
                f"Use 'trailytics profile use <other>' to select another default before deleting.",
                err=True,
            )
            raise click.exceptions.Exit(1)

    if not yes:
        try:
            click.confirm(
                f"Are you sure you want to delete profile '{name}'?",
                abort=True,
            )
        except click.Abort:
            click.echo("Aborted.")
            raise click.exceptions.Exit(0)

    try:
        storage.delete_profile(name)
    except (ProfileNotFoundError, ProfileValidationError) as e:
        click.echo(f"Error: {e}", err=True)
        raise click.exceptions.Exit(1)
    except ProfileStorageError as e:
        click.echo(f"Error: Storage failure: {e}", err=True)
        raise click.exceptions.Exit(1)

    click.echo(f"Profile '{name}' deleted successfully.")
