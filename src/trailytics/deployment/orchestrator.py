"""Python-native Docker Compose orchestrator for standalone Trailytics deployment."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

from trailytics.deployment.assets import (
    get_compose_file_path,
    verify_deployment_assets,
)
from trailytics.deployment.docker_client import DockerClient
from trailytics.exceptions import TrailyticsError
from trailytics.profiles.resolver import resolve_config

console = Console(highlight=False)

DEFAULT_PROJECT_NAME: str = "opik-opik"
DEFAULT_DASHBOARD_PORT: int = 5173
DEFAULT_TIMEOUT_SECONDS: int = 600

REQUIRED_SERVICES: List[str] = [
    "frontend",
    "backend",
    "python-backend",
    "clickhouse",
    "mysql",
    "redis",
    "minio",
    "zookeeper",
]


class StandaloneOrchestrator:
    """Manages the standalone Docker Compose lifecycle without requiring repository files."""

    def __init__(
        self,
        docker_client: Optional[DockerClient] = None,
        compose_file: Optional[Path] = None,
        project_name: str = DEFAULT_PROJECT_NAME,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.docker = docker_client or DockerClient()
        self.compose_file = compose_file or get_compose_file_path()
        # Enforce opik-opik identity invariant for data preservation
        self.project_name = project_name or DEFAULT_PROJECT_NAME
        self.port = port or int(os.environ.get("TRAILYTICS_DASHBOARD_PORT", DEFAULT_DASHBOARD_PORT))
        self.timeout = timeout or int(
            os.environ.get("TRAILYTICS_STARTUP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )

    # =========================================================================
    # Prerequisite Checks
    # =========================================================================

    def verify_prerequisites(self) -> Tuple[bool, Optional[str]]:
        """Verify Docker and Docker Compose v2 prerequisites."""
        if not self.docker.is_docker_installed():
            return (
                False,
                "Docker is not installed or not found in PATH.\n"
                "Please install Docker (https://docs.docker.com/get-docker/) and try again.",
            )

        daemon_ok, daemon_msg = self.docker.is_daemon_running()
        if not daemon_ok:
            return (
                False,
                f"Docker daemon is not accessible: {daemon_msg}\n"
                "Ensure the Docker service is running and your user has permission to access the Docker socket.",
            )

        compose_ok, compose_msg = self.docker.is_compose_v2_available()
        if not compose_ok:
            return (
                False,
                f"Docker Compose v2 is required: {compose_msg}\n"
                "Please install Docker Compose v2 (e.g., 'docker compose version' >= 2.20).",
            )

        missing_assets = verify_deployment_assets()
        if missing_assets:
            return (
                False,
                "Bundled deployment assets are missing or corrupted:\n  - "
                + "\n  - ".join(missing_assets),
            )

        return True, None

    # =========================================================================
    # Frontend Image Resolution with Fallback
    # =========================================================================

    def resolve_frontend_image(self) -> Tuple[str, str, Optional[str]]:
        """Resolve the frontend container image and pull policy.

        Returns:
            Tuple of (image_reference, pull_policy, optional_warning_message)
        """
        # 1. Check local branded image
        if self.docker.image_exists_locally("trailytics-frontend:2.2.138"):
            return ("trailytics-frontend:2.2.138", "never", None)

        # 2. Check local Docker Hub branded image
        if self.docker.image_exists_locally("avijitnpm/trailytics-frontend:2.2.138"):
            return ("avijitnpm/trailytics-frontend:2.2.138", "never", None)

        # 3. Try pulling Docker Hub branded image
        if self.docker.try_pull_image("avijitnpm/trailytics-frontend:2.2.138"):
            return ("avijitnpm/trailytics-frontend:2.2.138", "if_not_present", None)

        # 4. Fallback to official upstream Opik image
        upstream_img = "ghcr.io/comet-ml/opik/opik-frontend:2.2.138"
        if self.docker.image_exists_locally(upstream_img) or self.docker.try_pull_image(upstream_img):
            warning = (
                "Warning: Trailytics branded frontend image ('avijitnpm/trailytics-frontend:2.2.138') "
                "is not available locally or in the container registry.\n"
                "Falling back to official Opik 2.2.138 frontend ('ghcr.io/comet-ml/opik/opik-frontend:2.2.138').\n"
                "The dashboard UI will operate with default upstream branding."
            )
            return (upstream_img, "if_not_present", warning)

        # 5. Neither image available
        raise TrailyticsError(
            "Neither the Trailytics frontend image ('avijitnpm/trailytics-frontend:2.2.138') "
            "nor the upstream Opik frontend ('ghcr.io/comet-ml/opik/opik-frontend:2.2.138') "
            "could be found locally or pulled from the registry."
        )

    # =========================================================================
    # Lifecycle Operations
    # =========================================================================

    def start(self) -> int:
        """Start Trailytics containers standalone and wait for healthy status."""
        ok, err = self.verify_prerequisites()
        if not ok:
            click.echo(f"Trailytics Error: {err}", err=True)
            return 1

        # Check existing running state
        containers = self.docker.get_compose_containers(self.project_name)
        running_names = [c.get("Name", "") for c in containers if c.get("State") == "running"]
        if f"{self.project_name}-frontend-1" in running_names:
            click.echo(f"Trailytics is already running at http://localhost:{self.port}")
            return 0

        # Check port conflict
        if self.docker.is_port_in_use(self.port):
            click.echo(
                f"Trailytics Error: Port {self.port} is already in use by another process.\n"
                f"Stop the conflicting service or set TRAILYTICS_DASHBOARD_PORT to a different port.",
                err=True,
            )
            return 1

        # Resolve frontend image
        try:
            frontend_img, pull_policy, warning_msg = self.resolve_frontend_image()
            if warning_msg:
                click.echo(warning_msg, err=True)
        except TrailyticsError as e:
            click.echo(f"Trailytics Error: {e}", err=True)
            return 1

        env = {
            "COMPOSE_PROJECT_NAME": self.project_name,
            "OPIK_VERSION": "2.2.138",
            "NGINX_PORT": str(self.port),
            "CREATE_DEMO_DATA": os.environ.get("CREATE_DEMO_DATA", "false"),
            "OPIK_USAGE_REPORT_ENABLED": "false",
            "TRAILYTICS_FRONTEND_IMAGE": frontend_img,
            "TRAILYTICS_FRONTEND_PULL_POLICY": pull_policy,
        }

        click.echo("Starting Trailytics containers in standalone mode...")
        res = self.docker.run_compose(
            project=self.project_name,
            compose_file=self.compose_file,
            compose_args=["--profile", "opik", "up", "-d"],
            env=env,
            capture_output=True,
        )
        if res.returncode != 0:
            click.echo(
                f"Trailytics Error: Failed to start containers:\n{res.stderr.strip()}",
                err=True,
            )
            return res.returncode

        # Poll container health
        click.echo("Waiting for services to become healthy...")
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            containers = self.docker.get_compose_containers(self.project_name)
            if self._all_required_services_healthy(containers):
                click.echo(f"\nTrailytics is ready at http://localhost:{self.port}")
                return 0
            time.sleep(2)

        # Timeout reached
        click.echo(
            f"\nTrailytics Error: Startup timed out after {self.timeout}s.\n"
            "Diagnostics for unhealthy containers:",
            err=True,
        )
        self._print_unhealthy_diagnostics(containers)
        return 1

    def stop(self) -> int:
        """Stop Trailytics containers safely without removing persistent volumes."""
        ok, err = self.verify_prerequisites()
        if not ok:
            click.echo(f"Trailytics Error: {err}", err=True)
            return 1

        click.echo("Stopping Trailytics containers...")
        res = self.docker.run_compose(
            project=self.project_name,
            compose_file=self.compose_file,
            compose_args=["--profile", "opik", "stop"],
            capture_output=True,
        )
        if res.returncode != 0:
            click.echo(f"Trailytics Error: Failed to stop containers:\n{res.stderr.strip()}", err=True)
            return res.returncode

        click.echo("Trailytics deployment stopped. Persistent data has been preserved.")
        return 0

    def restart(self) -> int:
        """Restart Trailytics deployment by stopping and starting containers."""
        stop_code = self.stop()
        if stop_code != 0:
            click.echo("Trailytics Error: Stopping deployment failed; aborting restart.", err=True)
            return stop_code
        return self.start()

    def status(self) -> int:
        """Display status of Trailytics containers in standalone mode."""
        ok, err = self.verify_prerequisites()
        if not ok:
            click.echo(f"Trailytics Error: {err}", err=True)
            return 1

        containers = self.docker.get_compose_containers(self.project_name)
        if not containers:
            click.echo("Trailytics Deployment Status (Mode: Standalone)")
            click.echo(f"Project: {self.project_name} | Dashboard: http://localhost:{self.port}")
            click.echo("No containers are currently running for this deployment.")
            click.echo("Run 'trailytics start' to start Trailytics.")
            return 0

        table = Table(title=f"Trailytics Deployment Status (Mode: Standalone)")
        table.add_column("Service", style="bold cyan")
        table.add_column("Container", style="dim")
        table.add_column("State", justify="center")
        table.add_column("Health", justify="center")
        table.add_column("Status")

        all_healthy = True
        for c in sorted(containers, key=lambda x: x.get("Service", "")):
            svc = c.get("Service", "unknown")
            name = c.get("Name", "unknown")
            state = c.get("State", "unknown")
            health = c.get("Health", "") or ("running" if state == "running" else "stopped")
            status_desc = c.get("Status", "")

            # Color coding
            if health == "healthy" or state == "running":
                health_style = "[green]" + health + "[/green]"
            elif state == "exited" and c.get("ExitCode") == 0:
                health_style = "[yellow]completed[/yellow]"
            else:
                health_style = "[red]" + (health or state) + "[/red]"
                all_healthy = False

            table.add_row(svc, name, state, health_style, status_desc)

        console.print(table)
        click.echo(f"Dashboard: http://localhost:{self.port} | Overall: {'HEALTHY' if all_healthy else 'DEGRADED'}")
        return 0

    def logs(self, log_args: List[str]) -> int:
        """Stream or retrieve logs for Trailytics containers in standalone mode."""
        ok, err = self.verify_prerequisites()
        if not ok:
            click.echo(f"Trailytics Error: {err}", err=True)
            return 1

        cmd_args = ["--profile", "opik", "logs"] + log_args
        return self.docker.stream_compose(
            project=self.project_name,
            compose_file=self.compose_file,
            compose_args=cmd_args,
        )

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _all_required_services_healthy(self, containers: List[Dict[str, Any]]) -> bool:
        """Check if all required services are healthy or running."""
        by_service: Dict[str, Dict[str, Any]] = {c.get("Service", ""): c for c in containers}

        for req in REQUIRED_SERVICES:
            if req not in by_service:
                return False
            c = by_service[req]
            state = c.get("State", "")
            health = c.get("Health", "")
            if state != "running":
                return False
            if health and health != "healthy":
                return False

        return True

    def _print_unhealthy_diagnostics(self, containers: List[Dict[str, Any]]) -> None:
        """Print recent log lines for any unhealthy or non-running containers."""
        for c in containers:
            name = c.get("Name", "")
            state = c.get("State", "")
            health = c.get("Health", "")
            if health != "healthy" and state != "running":
                click.echo(f"\n--- Container: {name} (State: {state}, Health: {health}) ---", err=True)
                logs = self.docker.get_container_logs(name, tail=30)
                click.echo(logs or "(no logs recorded)", err=True)
