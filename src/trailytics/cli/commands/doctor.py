"""Doctor command for Trailytics CLI - comprehensive read-only diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple
import urllib.error
import urllib.request

import click

from trailytics.cli.runner import (
    find_repository_root,
    get_repository_metadata,
    is_development_mode,
    is_valid_repository_root,
)
from trailytics.deployment.assets import get_compose_file_path, verify_deployment_assets
from trailytics.exceptions import RepositoryNotFoundError


class CheckStatus(str, Enum):
    """Status outcomes for diagnostic checks."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class DiagnosticCheck:
    """Individual diagnostic check result."""

    name: str
    status: CheckStatus
    message: str = ""


# Expected 8 runtime containers for full Opik/Trailytics profile
REQUIRED_RUNTIME_SERVICES: List[str] = [
    "frontend",
    "backend",
    "clickhouse",
    "minio",
    "python-backend",
    "mysql",
    "zookeeper",
    "redis",
]

REQUIRED_LIFECYCLE_SCRIPTS: List[str] = [
    "start.sh",
    "stop.sh",
    "status.sh",
    "lib.sh",
    "build-frontend.sh",
    "install.sh",
    "logs.sh",
]


def check_repository(repo_dir: Optional[Path]) -> List[DiagnosticCheck]:
    """Inspect repository root, markers, config, and submodule integrity."""
    checks: List[DiagnosticCheck] = []

    # 1. Repository discovery
    if repo_dir is None:
        checks.append(
            DiagnosticCheck(
                name="Repository detected",
                status=CheckStatus.FAIL,
                message="Trailytics repository root could not be located",
            )
        )
        return checks



    checks.append(
        DiagnosticCheck(
            name="Repository detected",
            status=CheckStatus.PASS,
            message=str(repo_dir),
        )
    )

    # 2. Required markers
    if is_valid_repository_root(repo_dir):
        checks.append(
            DiagnosticCheck(
                name="Required repository markers",
                status=CheckStatus.PASS,
                message="All required markers present",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="Required repository markers",
                status=CheckStatus.FAIL,
                message="One or more markers missing (trailytics/, config/, upstream/opik/, pyproject.toml)",
            )
        )

    # 3. Configuration file
    env_file = repo_dir / "config" / "trailytics.env"
    if env_file.is_file():
        metadata = get_repository_metadata(repo_dir)
        opik_ver = metadata.get("OPIK_VERSION", "unknown")
        compose_proj = metadata.get("TRAILYTICS_COMPOSE_PROJECT", "opik-opik")
        checks.append(
            DiagnosticCheck(
                name="Configuration found",
                status=CheckStatus.PASS,
                message=f"OPIK_VERSION={opik_ver}, TRAILYTICS_COMPOSE_PROJECT={compose_proj}",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="Configuration found",
                status=CheckStatus.FAIL,
                message="Missing config/trailytics.env",
            )
        )

    # 4. Lifecycle scripts
    missing_scripts = [
        s for s in REQUIRED_LIFECYCLE_SCRIPTS if not (repo_dir / "trailytics" / s).is_file()
    ]
    if not missing_scripts:
        checks.append(
            DiagnosticCheck(
                name="Required lifecycle scripts",
                status=CheckStatus.PASS,
                message=f"{len(REQUIRED_LIFECYCLE_SCRIPTS)}/{len(REQUIRED_LIFECYCLE_SCRIPTS)} present",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="Required lifecycle scripts",
                status=CheckStatus.FAIL,
                message=f"Missing: {', '.join(missing_scripts)}",
            )
        )

    # 5. Upstream submodule initialized
    submodule_git = repo_dir / "upstream" / "opik" / ".git"
    submodule_dir = repo_dir / "upstream" / "opik"
    if submodule_git.exists():
        checks.append(
            DiagnosticCheck(
                name="Upstream submodule initialized",
                status=CheckStatus.PASS,
                message="Submodule git directory present",
            )
        )

        # 6. Pinned commit verified
        metadata = get_repository_metadata(repo_dir)
        expected_commit = metadata.get("OPIK_COMMIT", "28192d8ffe85299f5c44032f705a9e518e6d1189")
        try:
            commit_res = subprocess.run(
                ["git", "-C", str(submodule_dir), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            actual_commit = commit_res.stdout.strip()
            if commit_res.returncode == 0 and actual_commit == expected_commit:
                checks.append(
                    DiagnosticCheck(
                        name="Pinned Opik commit verified",
                        status=CheckStatus.PASS,
                        message=f"{actual_commit[:12]} ({expected_commit[:12]})",
                    )
                )
            else:
                checks.append(
                    DiagnosticCheck(
                        name="Pinned Opik commit verified",
                        status=CheckStatus.FAIL,
                        message=f"Expected {expected_commit[:12]}, got {actual_commit[:12] if actual_commit else 'unknown'}",
                    )
                )
        except OSError as e:
            checks.append(
                DiagnosticCheck(
                    name="Pinned Opik commit verified",
                    status=CheckStatus.FAIL,
                    message=f"Failed to query git: {e}",
                )
            )

        # 7. Submodule cleanliness
        try:
            status_res = subprocess.run(
                ["git", "-C", str(submodule_dir), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
            )
            if status_res.returncode == 0 and not status_res.stdout.strip():
                checks.append(
                    DiagnosticCheck(
                        name="Upstream working tree clean",
                        status=CheckStatus.PASS,
                        message="Working tree clean (no local modifications)",
                    )
                )
            else:
                checks.append(
                    DiagnosticCheck(
                        name="Upstream working tree clean",
                        status=CheckStatus.FAIL,
                        message="Submodule has unstaged/uncommitted modifications",
                    )
                )
        except OSError as e:
            checks.append(
                DiagnosticCheck(
                    name="Upstream working tree clean",
                    status=CheckStatus.FAIL,
                    message=f"Failed to run git status: {e}",
                )
            )
    else:
        checks.append(
            DiagnosticCheck(
                name="Upstream submodule initialized",
                status=CheckStatus.FAIL,
                message="Submodule not initialized (run ./trailytics/install.sh)",
            )
        )
        checks.append(
            DiagnosticCheck(
                name="Pinned Opik commit verified",
                status=CheckStatus.SKIP,
                message="Submodule not initialized",
            )
        )
        checks.append(
            DiagnosticCheck(
                name="Upstream working tree clean",
                status=CheckStatus.SKIP,
                message="Submodule not initialized",
            )
        )

    return checks


def check_standalone_package() -> List[DiagnosticCheck]:
    """Inspect standalone package assets and deployment distribution."""
    checks: List[DiagnosticCheck] = [
        DiagnosticCheck(
            name="Execution mode",
            status=CheckStatus.PASS,
            message="Standalone (Packaged Distribution)",
        )
    ]
    missing = verify_deployment_assets()
    if not missing:
        checks.append(
            DiagnosticCheck(
                name="Bundled deployment assets",
                status=CheckStatus.PASS,
                message="Compose manifest and configuration templates present",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="Bundled deployment assets",
                status=CheckStatus.FAIL,
                message=f"Missing assets: {', '.join(missing)}",
            )
        )
    return checks


def check_docker(repo_dir: Optional[Path]) -> Tuple[List[DiagnosticCheck], bool]:
    """Inspect Docker CLI, daemon accessibility, compose v2, and compose config."""
    checks: List[DiagnosticCheck] = []
    docker_available = True

    # 1. Docker CLI
    try:
        cli_res = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cli_res.returncode == 0:
            ver = cli_res.stdout.strip()
            checks.append(
                DiagnosticCheck(
                    name="Docker CLI installed",
                    status=CheckStatus.PASS,
                    message=ver,
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    name="Docker CLI installed",
                    status=CheckStatus.FAIL,
                    message="Command 'docker --version' exited non-zero",
                )
            )
            docker_available = False
    except OSError:
        checks.append(
            DiagnosticCheck(
                name="Docker CLI installed",
                status=CheckStatus.FAIL,
                message="Docker CLI binary not found in PATH",
            )
        )
        docker_available = False

    if not docker_available:
        checks.append(
            DiagnosticCheck(
                name="Docker daemon available",
                status=CheckStatus.SKIP,
                message="Docker CLI unavailable",
            )
        )
        checks.append(
            DiagnosticCheck(
                name="Docker Compose v2 available",
                status=CheckStatus.SKIP,
                message="Docker CLI unavailable",
            )
        )
        checks.append(
            DiagnosticCheck(
                name="Compose configuration valid",
                status=CheckStatus.SKIP,
                message="Docker CLI unavailable",
            )
        )
        return checks, False

    # 2. Docker daemon
    try:
        info_res = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            check=False,
        )
        if info_res.returncode == 0:
            checks.append(
                DiagnosticCheck(
                    name="Docker daemon available",
                    status=CheckStatus.PASS,
                    message="Docker daemon accessible and responding",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    name="Docker daemon available",
                    status=CheckStatus.FAIL,
                    message="Docker daemon not running or socket inaccessible",
                )
            )
            docker_available = False
    except OSError as e:
        checks.append(
            DiagnosticCheck(
                name="Docker daemon available",
                status=CheckStatus.FAIL,
                message=f"Failed to query Docker daemon: {e}",
            )
        )
        docker_available = False

    # 3. Docker Compose v2
    try:
        compose_res = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if compose_res.returncode == 0:
            checks.append(
                DiagnosticCheck(
                    name="Docker Compose v2 available",
                    status=CheckStatus.PASS,
                    message=compose_res.stdout.strip(),
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    name="Docker Compose v2 available",
                    status=CheckStatus.FAIL,
                    message="Docker Compose v2 is required but not responding",
                )
            )
    except OSError:
        checks.append(
            DiagnosticCheck(
                name="Docker Compose v2 available",
                status=CheckStatus.FAIL,
                message="Docker Compose plugin missing",
            )
        )

    # 4. Compose configuration validation
    if docker_available:
        if repo_dir is not None:
            compose_file = repo_dir / "upstream" / "opik" / "deployment" / "docker-compose" / "docker-compose.yaml"
            metadata = get_repository_metadata(repo_dir)
            project_name = metadata.get("TRAILYTICS_COMPOSE_PROJECT", "opik-opik")
        else:
            compose_file = get_compose_file_path()
            project_name = "opik-opik"

        if compose_file.is_file():
            try:
                cfg_res = subprocess.run(
                    [
                        "docker",
                        "compose",
                        "-p",
                        project_name,
                        "-f",
                        str(compose_file),
                        "--profile",
                        "opik",
                        "config",
                        "--quiet",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if cfg_res.returncode == 0:
                    checks.append(
                        DiagnosticCheck(
                            name="Compose configuration valid",
                            status=CheckStatus.PASS,
                            message="Compose files and profiles parsed successfully",
                        )
                    )
                else:
                    err_msg = cfg_res.stderr.strip() or "Compose config validation error"
                    checks.append(
                        DiagnosticCheck(
                            name="Compose configuration valid",
                            status=CheckStatus.FAIL,
                            message=err_msg.split("\n")[0],
                        )
                    )
            except OSError as e:
                checks.append(
                    DiagnosticCheck(
                        name="Compose configuration valid",
                        status=CheckStatus.FAIL,
                        message=f"Failed to validate compose config: {e}",
                    )
                )
        else:
            checks.append(
                DiagnosticCheck(
                    name="Compose configuration valid",
                    status=CheckStatus.FAIL,
                    message=f"Missing compose file: {compose_file}",
                )
            )
    else:
        checks.append(
            DiagnosticCheck(
                name="Compose configuration valid",
                status=CheckStatus.SKIP,
                message="Docker daemon unavailable",
            )
        )

    return checks, docker_available


def check_deployment(
    repo_dir: Optional[Path],
    docker_available: bool,
    project_name: str,
) -> Tuple[List[DiagnosticCheck], bool]:
    """Inspect Compose project identity, foreign container detection, and runtime services health."""
    checks: List[DiagnosticCheck] = []
    deployment_running = False

    if not docker_available:
        checks.append(
            DiagnosticCheck(
                name="Project identity verified",
                status=CheckStatus.SKIP,
                message="Docker daemon unavailable",
            )
        )
        checks.append(
            DiagnosticCheck(
                name="Runtime services healthy",
                status=CheckStatus.SKIP,
                message="Docker daemon unavailable",
            )
        )
        return checks, False

    # 1. Project identity & foreign containers check
    upstream_dir = str(repo_dir / "upstream" / "opik") if repo_dir else ""
    try:
        ps_res = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={project_name}",
                "--format",
                '{{.Label "com.docker.compose.project.working_dir"}}',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if ps_res.returncode == 0:
            dirs = set(line.strip() for line in ps_res.stdout.splitlines() if line.strip())
            if is_development_mode() and repo_dir:
                valid_dirs = {upstream_dir, f"{upstream_dir}/deployment/docker-compose"}
                foreign_dirs = [d for d in dirs if d not in valid_dirs]
            else:
                # In standalone mode, containers may originate from the bundled
                # deployment directory or an existing compatible deployment.
                # A conflict exists only if containers are split across multiple directories.
                if len(dirs) > 1:
                    foreign_dirs = list(dirs)
                else:
                    foreign_dirs = []

            if foreign_dirs:
                if is_development_mode() and repo_dir:
                    msg = f"Conflicting containers detected from foreign directory: {', '.join(foreign_dirs)}"
                else:
                    msg = f"Conflicting containers detected across multiple directories: {', '.join(foreign_dirs)}"
                checks.append(
                    DiagnosticCheck(
                        name="Project identity verified",
                        status=CheckStatus.FAIL,
                        message=msg,
                    )
                )
            else:
                checks.append(
                    DiagnosticCheck(
                        name="Project identity verified",
                        status=CheckStatus.PASS,
                        message=f"Project '{project_name}' is isolated and consistent",
                    )
                )
        else:
            checks.append(
                DiagnosticCheck(
                    name="Project identity verified",
                    status=CheckStatus.FAIL,
                    message="Failed to query containers for project",
                )
            )
    except OSError as e:
        checks.append(
            DiagnosticCheck(
                name="Project identity verified",
                status=CheckStatus.FAIL,
                message=f"Docker query failed: {e}",
            )
        )

    # 2. Runtime services state & health
    container_statuses: Dict[str, Tuple[str, str, str]] = {}
    for service in REQUIRED_RUNTIME_SERVICES:
        c_name = f"{project_name}-{service}-1"
        try:
            inspect_res = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.ExitCode}}",
                    c_name,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if inspect_res.returncode == 0:
                parts = inspect_res.stdout.strip().split("|")
                status = parts[0] if len(parts) > 0 else "unknown"
                health = parts[1] if len(parts) > 1 else "none"
                code = parts[2] if len(parts) > 2 else "0"
                container_statuses[service] = (status, health, code)
            else:
                container_statuses[service] = ("missing", "none", "1")
        except OSError:
            container_statuses[service] = ("error", "none", "1")

    # Evaluate runtime services
    healthy_count = sum(
        1
        for s, (status, health, _) in container_statuses.items()
        if status == "running" and health in ("healthy", "none")
    )
    running_count = sum(
        1 for s, (status, _, _) in container_statuses.items() if status == "running"
    )

    if healthy_count == len(REQUIRED_RUNTIME_SERVICES):
        checks.append(
            DiagnosticCheck(
                name="Runtime services healthy",
                status=CheckStatus.PASS,
                message=f"All {len(REQUIRED_RUNTIME_SERVICES)} runtime services healthy",
            )
        )
        deployment_running = True
    elif running_count == 0:
        checks.append(
            DiagnosticCheck(
                name="Runtime services healthy",
                status=CheckStatus.WARN,
                message="Deployment is stopped (0/8 runtime services running)",
            )
        )
        deployment_running = False
    else:
        unhealthy_services = [
            f"{s} ({status}/{health})"
            for s, (status, health, _) in container_statuses.items()
            if not (status == "running" and health in ("healthy", "none"))
        ]
        checks.append(
            DiagnosticCheck(
                name="Runtime services healthy",
                status=CheckStatus.FAIL,
                message=f"Unhealthy/missing: {', '.join(unhealthy_services)}",
            )
        )
        deployment_running = True

    return checks, deployment_running


def check_connectivity(
    dashboard_port: str,
    deployment_running: bool,
) -> List[DiagnosticCheck]:
    """Verify HTTP reachability for dashboard and backend API endpoints."""
    checks: List[DiagnosticCheck] = []

    if not deployment_running:
        checks.append(
            DiagnosticCheck(
                name="Dashboard reachable",
                status=CheckStatus.SKIP,
                message="Deployment is not running",
            )
        )
        checks.append(
            DiagnosticCheck(
                name="Backend API reachable",
                status=CheckStatus.SKIP,
                message="Deployment is not running",
            )
        )
        return checks



    # 1. Dashboard URL
    dashboard_url = f"http://localhost:{dashboard_port}/"
    try:
        req = urllib.request.Request(dashboard_url, method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status < 400:
                checks.append(
                    DiagnosticCheck(
                        name="Dashboard reachable",
                        status=CheckStatus.PASS,
                        message=f"{dashboard_url} returned HTTP {resp.status}",
                    )
                )
            else:
                checks.append(
                    DiagnosticCheck(
                        name="Dashboard reachable",
                        status=CheckStatus.FAIL,
                        message=f"{dashboard_url} returned HTTP {resp.status}",
                    )
                )
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        checks.append(
            DiagnosticCheck(
                name="Dashboard reachable",
                status=CheckStatus.FAIL,
                message=f"Failed to connect to {dashboard_url}: {e}",
            )
        )

    # 2. Backend Healthcheck URL
    backend_url = f"http://localhost:{dashboard_port}/api/health-check"
    try:
        req = urllib.request.Request(backend_url, method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status < 400:
                checks.append(
                    DiagnosticCheck(
                        name="Backend API reachable",
                        status=CheckStatus.PASS,
                        message=f"{backend_url} returned HTTP {resp.status}",
                    )
                )
            else:
                checks.append(
                    DiagnosticCheck(
                        name="Backend API reachable",
                        status=CheckStatus.FAIL,
                        message=f"{backend_url} returned HTTP {resp.status}",
                    )
                )
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        checks.append(
            DiagnosticCheck(
                name="Backend API reachable",
                status=CheckStatus.FAIL,
                message=f"Failed to connect to {backend_url}: {e}",
            )
        )

    return checks




def run_doctor() -> Tuple[Dict[str, List[DiagnosticCheck]], int]:
    """Execute all diagnostic checks across Repository, Docker, Deployment, and Connectivity."""
    categories: Dict[str, List[DiagnosticCheck]] = {}

    # Discover repository
    repo_dir: Optional[Path] = None
    try:
        repo_dir = find_repository_root()
    except RepositoryNotFoundError:
        repo_dir = None

    metadata = get_repository_metadata(repo_dir) if repo_dir else {}
    project_name = metadata.get("TRAILYTICS_COMPOSE_PROJECT", "opik-opik")
    dashboard_port = metadata.get("TRAILYTICS_DASHBOARD_PORT", "5173")

    # Category A: Repository / Package
    if is_development_mode() and repo_dir is not None:
        categories["Repository"] = check_repository(repo_dir)
    else:
        categories["Repository"] = check_standalone_package()

    # Category B: Docker
    docker_checks, docker_available = check_docker(repo_dir)
    categories["Docker"] = docker_checks

    # Category C: Deployment
    deployment_checks, deployment_running = check_deployment(
        repo_dir, docker_available, project_name
    )
    categories["Deployment"] = deployment_checks

    # Category D: Connectivity
    categories["Connectivity"] = check_connectivity(dashboard_port, deployment_running)

    # Calculate exit code: 1 if any FAIL, 0 otherwise
    has_failures = any(
        c.status == CheckStatus.FAIL for checks in categories.values() for c in checks
    )
    exit_code = 1 if has_failures else 0

    return categories, exit_code


def format_doctor_report(categories: Dict[str, List[DiagnosticCheck]]) -> str:
    """Format diagnostic checks into structured readable terminal output."""
    mode_str = "Development" if is_development_mode() else "Standalone"
    lines: List[str] = [f"Trailytics Doctor (Mode: {mode_str})\n"]

    total_pass = 0
    total_warn = 0
    total_fail = 0
    total_skip = 0

    status_styles = {
        CheckStatus.PASS: click.style("[PASS]", fg="green", bold=True),
        CheckStatus.WARN: click.style("[WARN]", fg="yellow", bold=True),
        CheckStatus.FAIL: click.style("[FAIL]", fg="red", bold=True),
        CheckStatus.SKIP: click.style("[SKIP]", fg="bright_black"),
    }

    for category, checks in categories.items():
        lines.append(category)
        for check in checks:
            tag = status_styles.get(check.status, f"[{check.status.value}]")
            if check.status == CheckStatus.PASS:
                total_pass += 1
            elif check.status == CheckStatus.WARN:
                total_warn += 1
            elif check.status == CheckStatus.FAIL:
                total_fail += 1
            elif check.status == CheckStatus.SKIP:
                total_skip += 1

            detail = f" - {check.message}" if check.message else ""
            lines.append(f"  {tag} {check.name}{detail}")
        lines.append("")

    if total_fail > 0:
        result_text = click.style(
            f"Result: {total_fail} check(s) failed ({total_pass} passed, {total_warn} warnings, {total_skip} skipped).",
            fg="red",
            bold=True,
        )
    elif total_warn > 0:
        result_text = click.style(
            f"Result: Completed with {total_warn} warning(s) ({total_pass} passed, {total_skip} skipped).",
            fg="yellow",
            bold=True,
        )
    else:
        result_text = click.style(
            f"Result: All {total_pass} checks passed.",
            fg="green",
            bold=True,
        )

    lines.append(result_text)
    return "\n".join(lines)


@click.command("doctor", help="Perform comprehensive read-only diagnostics on Trailytics.")
def doctor_cmd() -> None:
    """Run non-mutating diagnostics across repository, Docker, deployment, and connectivity."""
    categories, exit_code = run_doctor()
    report = format_doctor_report(categories)
    click.echo(report)
    if exit_code != 0:
        raise click.exceptions.Exit(exit_code)
