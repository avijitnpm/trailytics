"""Trailytics CLI runner and repository discovery utilities."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple

import click

from trailytics.exceptions import RepositoryNotFoundError, ScriptExecutionError

# Required repository markers to validate a Trailytics root directory
REQUIRED_REPO_MARKERS: List[Tuple[str, bool]] = [
    ("trailytics", True),             # Directory containing lifecycle scripts
    ("config/trailytics.env", False), # Environment configuration file
    ("upstream/opik", True),          # Upstream submodule directory
    ("pyproject.toml", False),        # Python package specification
]


def is_valid_repository_root(path: Path) -> bool:
    """Check if the given path contains all required markers of a Trailytics repository."""
    try:
        resolved = path.resolve()
        if not resolved.is_dir():
            return False

        for rel_path, is_dir in REQUIRED_REPO_MARKERS:
            target = resolved / rel_path
            if is_dir:
                if not target.is_dir():
                    return False
            else:
                if not target.is_file():
                    return False
        return True
    except (OSError, PermissionError):
        return False


def find_repository_root() -> Optional[Path]:
    """Discover the Trailytics repository root directory.

    Resolution precedence:
    1. Explicit TRAILYTICS_REPO_DIR environment variable (must be valid if set).
    2. Current working directory and its parent directories.
    3. CLI module/package location and its parent directories.

    Returns:
        Resolved absolute Path to repository root, or None if not found.

    Raises:
        RepositoryNotFoundError: If TRAILYTICS_REPO_DIR is explicitly set to an invalid path.
    """
    # 1. Explicit environment variable
    explicit_env = os.environ.get("TRAILYTICS_REPO_DIR")
    if explicit_env:
        resolved = Path(explicit_env).resolve()
        if not is_valid_repository_root(resolved):
            raise RepositoryNotFoundError(
                f"Configured TRAILYTICS_REPO_DIR='{explicit_env}' is not a valid Trailytics repository.\n"
                f"Missing required markers (expected: trailytics/, config/trailytics.env, upstream/opik/, pyproject.toml)."
            )
        return resolved

    # 2. Current working directory and its parents
    try:
        current = Path.cwd().resolve()
        for candidate in [current, *current.parents]:
            if is_valid_repository_root(candidate):
                return candidate
    except (OSError, PermissionError):
        pass

    # 3. CLI module location and its parents
    try:
        module_dir = Path(__file__).resolve().parent
        for candidate in [module_dir, *module_dir.parents]:
            if is_valid_repository_root(candidate):
                return candidate
    except (OSError, PermissionError):
        pass

    return None


def get_repository_root() -> Path:
    """Get the validated repository root or raise RepositoryNotFoundError."""
    repo = find_repository_root()
    if repo is None:
        raise RepositoryNotFoundError(
            "Trailytics repository could not be located.\n\n"
            "The CLI requires access to the Trailytics deployment repository.\n\n"
            "Run this command from inside the repository or set:\n\n"
            "TRAILYTICS_REPO_DIR=/path/to/trailytics"
        )
    return repo


def is_development_mode() -> bool:
    """Determine whether the CLI is running in Development mode or Standalone mode.

    Returns True if running inside a valid repository checkout (unless forced to standalone
    via TRAILYTICS_DEPLOYMENT_MODE='standalone').
    Returns False if outside a repository or if TRAILYTICS_DEPLOYMENT_MODE is standalone.
    """
    mode_override = os.environ.get("TRAILYTICS_DEPLOYMENT_MODE", "").strip().lower()
    if mode_override in {"development", "repo", "dev"}:
        return True
    if mode_override in {"standalone", "packaged", "pkg"}:
        return False

    try:
        root = find_repository_root()
        return root is not None
    except RepositoryNotFoundError:
        return False


def get_repository_metadata(repo_dir: Optional[Path] = None) -> Dict[str, str]:
    """Parse deployment metadata from config/trailytics.env."""
    if repo_dir is None:
        repo_dir = find_repository_root()

    if repo_dir is None:
        return {}

    env_file = repo_dir / "config" / "trailytics.env"
    metadata: Dict[str, str] = {}
    if not env_file.is_file():
        return metadata

    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    metadata[key.strip()] = val.strip().strip("'\"")
    except OSError:
        pass

    return metadata


def run_script(
    script_name: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute a Trailytics shell script using safe subprocess invocation.

    Args:
        script_name: Name of script under trailytics/ (e.g. 'start.sh', 'stop.sh', 'status.sh').
        args: Optional list of command-line arguments.
        env: Optional additional environment variables.
        capture_output: If True, captures stdout/stderr instead of streaming to terminal.
        check: If True, raises ScriptExecutionError on non-zero exit code.

    Returns:
        subprocess.CompletedProcess object.

    Raises:
        RepositoryNotFoundError: If repository root cannot be found.
        FileNotFoundError: If the script does not exist.
        ScriptExecutionError: If script returns non-zero and check=True.
    """
    repo_dir = get_repository_root()
    script_path = repo_dir / "trailytics" / script_name

    if not script_path.is_file():
        raise FileNotFoundError(f"Trailytics script not found: {script_path}")

    cmd = ["bash", str(script_path)]
    if args:
        cmd.extend(args)

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            env=merged_env,
            capture_output=capture_output,
            text=True,
            check=False,
        )
    except OSError as e:
        raise ScriptExecutionError(f"Failed to execute script '{script_name}': {e}") from e

    if check and result.returncode != 0:
        msg = f"Script '{script_name}' exited with status {result.returncode}"
        if capture_output and result.stderr:
            msg += f"\nError output:\n{result.stderr.strip()}"
        raise ScriptExecutionError(msg, exit_code=result.returncode)

    return result


def execute_lifecycle_script(
    script_name: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    allow_interrupt: bool = False,
) -> int:
    """Execute a Trailytics lifecycle script, streaming output to terminal.

    Catches repository discovery errors, missing scripts, and execution errors cleanly
    without emitting Python tracebacks to the user.

    Args:
        script_name: Name of the script under trailytics/ (e.g. 'start.sh', 'stop.sh', 'status.sh').
        args: Optional list of command-line arguments.
        env: Optional environment variables dictionary.
        allow_interrupt: If True, KeyboardInterrupt exits cleanly with code 0 (for log following).
            If False (default), KeyboardInterrupt returns code 130 to reflect an aborted operation.

    Returns:
        The integer exit code of the process.
    """
    try:
        result = run_script(
            script_name,
            args=args,
            env=env,
            capture_output=False,
            check=False,
        )
        return result.returncode
    except RepositoryNotFoundError as e:
        click.echo(f"Trailytics Error: {e}", err=True)
        return 1
    except FileNotFoundError as e:
        click.echo(f"Trailytics Error: {e}", err=True)
        return 1
    except ScriptExecutionError as e:
        click.echo(f"Trailytics Error: {e}", err=True)
        return e.exit_code
    except OSError as e:
        click.echo(f"Trailytics Error: Failed to run '{script_name}': {e}", err=True)
        return 1
    except KeyboardInterrupt:
        if allow_interrupt:
            return 0
        click.echo(f"\nTrailytics: operation '{script_name}' interrupted by user.", err=True)
        return 130
