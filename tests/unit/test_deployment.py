"""Unit tests for Trailytics standalone deployment assets, orchestrator, and dual-mode execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest import mock
import pytest
from click.testing import CliRunner

from trailytics.cli.main import cli
from trailytics.cli.runner import is_development_mode
from trailytics.deployment.assets import (
    get_clickhouse_config_dir,
    get_compose_file_path,
    get_deployment_dir,
    get_nginx_config_path,
    verify_deployment_assets,
)
from trailytics.deployment.docker_client import DockerClient
from trailytics.deployment.orchestrator import (
    DEFAULT_DASHBOARD_PORT,
    DEFAULT_PROJECT_NAME,
    StandaloneOrchestrator,
)
from trailytics.exceptions import TrailyticsError


# ============================================================================
# 1. Bundled Deployment Assets Tests
# ============================================================================


def test_deployment_assets_exist():
    """Verify all bundled deployment files exist in the package."""
    dep_dir = get_deployment_dir()
    assert dep_dir.is_dir()

    compose_file = get_compose_file_path()
    assert compose_file.is_file()
    assert "opik-opik" in compose_file.read_text()

    nginx_conf = get_nginx_config_path()
    assert nginx_conf.is_file()
    assert "upstream backend" in nginx_conf.read_text()

    ch_dir = get_clickhouse_config_dir()
    assert ch_dir.is_dir()
    assert (ch_dir / "additional_config.xml").is_file()
    assert (ch_dir / "users.d" / "distributed_insert_queue.xml").is_file()
    assert (ch_dir / "users.d" / "enable_time_type.xml").is_file()

    # Asset verification helper should return zero missing assets
    missing = verify_deployment_assets()
    assert missing == []


# ============================================================================
# 2. Dual-Mode Detection Tests
# ============================================================================


def test_is_development_mode_auto_detection(tmp_path):
    """Verify is_development_mode detects repository presence."""
    with mock.patch("trailytics.cli.runner.find_repository_root", return_value=tmp_path):
        assert is_development_mode() is True

    with mock.patch("trailytics.cli.runner.find_repository_root", return_value=None):
        assert is_development_mode() is False


def test_is_development_mode_override(monkeypatch, tmp_path):
    """Verify TRAILYTICS_DEPLOYMENT_MODE environment variable overrides auto-detection."""
    with mock.patch("trailytics.cli.runner.find_repository_root", return_value=tmp_path):
        monkeypatch.setenv("TRAILYTICS_DEPLOYMENT_MODE", "standalone")
        assert is_development_mode() is False

        monkeypatch.setenv("TRAILYTICS_DEPLOYMENT_MODE", "development")
        assert is_development_mode() is True


# ============================================================================
# 3. Docker Client & Prerequisite Checks
# ============================================================================


def test_docker_client_prerequisites():
    """Verify prerequisite checks with mocked docker CLI responses."""
    client = DockerClient()

    # Docker missing
    with mock.patch("shutil.which", return_value=None):
        assert client.is_docker_installed() is False
        daemon_ok, _ = client.is_daemon_running()
        assert daemon_ok is False
        compose_ok, _ = client.is_compose_v2_available()
        assert compose_ok is False

    # Docker present, daemon failed
    with mock.patch("shutil.which", return_value="/usr/bin/docker"), \
         mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=1, stderr="daemon is not running"
        )
        assert client.is_docker_installed() is True
        daemon_ok, msg = client.is_daemon_running()
        assert daemon_ok is False
        assert "daemon is not running" in msg

    # Compose v2 present
    with mock.patch("shutil.which", return_value="/usr/bin/docker"), \
         mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "compose", "version"], returncode=0, stdout="Docker Compose version v2.27.1\n"
        )
        compose_ok, msg = client.is_compose_v2_available()
        assert compose_ok is True
        assert "v2.27.1" in msg


# ============================================================================
# 4. Frontend Image Resolution & Fallback Tests
# ============================================================================


def test_resolve_frontend_image_local_cache():
    """Verify local branded image takes priority when available."""
    mock_client = mock.MagicMock(spec=DockerClient)
    mock_client.image_exists_locally.side_effect = lambda img: img == "trailytics-frontend:2.2.138"

    orchestrator = StandaloneOrchestrator(docker_client=mock_client)
    img, policy, warning = orchestrator.resolve_frontend_image()

    assert img == "trailytics-frontend:2.2.138"
    assert policy == "never"
    assert warning is None


def test_resolve_frontend_image_fallback_to_upstream():
    """Verify falling back to official upstream image when branded image is missing."""
    mock_client = mock.MagicMock(spec=DockerClient)
    # Neither local nor remote branded image exists; upstream exists locally or can be pulled
    mock_client.image_exists_locally.side_effect = lambda img: img == "ghcr.io/comet-ml/opik/opik-frontend:2.2.138"
    mock_client.try_pull_image.side_effect = lambda img: False

    orchestrator = StandaloneOrchestrator(docker_client=mock_client)
    img, policy, warning = orchestrator.resolve_frontend_image()

    assert img == "ghcr.io/comet-ml/opik/opik-frontend:2.2.138"
    assert policy == "if_not_present"
    assert warning is not None
    assert "Falling back to official Opik 2.2.138 frontend" in warning
    assert "trailytics-frontend" in warning


def test_resolve_frontend_image_both_missing_fails():
    """Verify error raised when neither branded nor upstream images can be obtained."""
    mock_client = mock.MagicMock(spec=DockerClient)
    mock_client.image_exists_locally.return_value = False
    mock_client.try_pull_image.return_value = False

    orchestrator = StandaloneOrchestrator(docker_client=mock_client)
    with pytest.raises(TrailyticsError, match="Neither the Trailytics frontend image"):
        orchestrator.resolve_frontend_image()


# ============================================================================
# 5. Standalone Lifecycle Operations Tests
# ============================================================================


def test_standalone_orchestrator_project_identity():
    """Verify standalone orchestrator strictly enforces opik-opik project identity."""
    orchestrator = StandaloneOrchestrator()
    assert orchestrator.project_name == "opik-opik"
    assert orchestrator.port == 5173


def test_standalone_start_prerequisite_failure():
    """Verify start fails cleanly when Docker prerequisites are not met."""
    mock_client = mock.MagicMock(spec=DockerClient)
    mock_client.is_docker_installed.return_value = False

    orchestrator = StandaloneOrchestrator(docker_client=mock_client)
    code = orchestrator.start()
    assert code == 1


def test_standalone_start_port_conflict():
    """Verify start detects foreign port conflict and aborts."""
    mock_client = mock.MagicMock(spec=DockerClient)
    mock_client.is_docker_installed.return_value = True
    mock_client.is_daemon_running.return_value = (True, "ok")
    mock_client.is_compose_v2_available.return_value = (True, "v2.20.0")
    mock_client.get_compose_containers.return_value = []
    # Port 5173 is in use by another process
    mock_client.is_port_in_use.return_value = True

    orchestrator = StandaloneOrchestrator(docker_client=mock_client)
    code = orchestrator.start()
    assert code == 1


def test_standalone_start_success():
    """Verify successful start executes docker compose up -d and polls health."""
    mock_client = mock.MagicMock(spec=DockerClient)
    mock_client.is_docker_installed.return_value = True
    mock_client.is_daemon_running.return_value = (True, "ok")
    mock_client.is_compose_v2_available.return_value = (True, "v2.20.0")
    mock_client.is_port_in_use.return_value = False
    mock_client.image_exists_locally.return_value = True

    # Simulate healthy containers
    healthy_containers = [
        {"Service": svc, "Name": f"opik-opik-{svc}-1", "State": "running", "Health": "healthy"}
        for svc in [
            "frontend", "backend", "python-backend", "clickhouse",
            "mysql", "redis", "minio", "zookeeper",
        ]
    ]
    # Initial call: not running; second call: healthy containers
    mock_client.get_compose_containers.side_effect = [[], healthy_containers]
    mock_client.run_compose.return_value = subprocess.CompletedProcess(args=[], returncode=0)

    orchestrator = StandaloneOrchestrator(docker_client=mock_client, timeout=5)
    code = orchestrator.start()
    assert code == 0

    # Verify command invocation had explicit project flag
    args, kwargs = mock_client.run_compose.call_args
    assert kwargs["project"] == "opik-opik"
    assert kwargs["compose_args"] == ["--profile", "opik", "up", "-d"]


def test_standalone_stop_success():
    """Verify stop runs docker compose stop without removing volumes."""
    mock_client = mock.MagicMock(spec=DockerClient)
    mock_client.is_docker_installed.return_value = True
    mock_client.is_daemon_running.return_value = (True, "ok")
    mock_client.is_compose_v2_available.return_value = (True, "v2.20.0")
    mock_client.run_compose.return_value = subprocess.CompletedProcess(args=[], returncode=0)

    orchestrator = StandaloneOrchestrator(docker_client=mock_client)
    code = orchestrator.stop()
    assert code == 0

    args, kwargs = mock_client.run_compose.call_args
    assert kwargs["project"] == "opik-opik"
    # STRICT: Must be 'stop', never 'down' or 'down -v'
    assert kwargs["compose_args"] == ["--profile", "opik", "stop"]


def test_standalone_status_output():
    """Verify status renders table with Standalone mode indicator."""
    mock_client = mock.MagicMock(spec=DockerClient)
    mock_client.is_docker_installed.return_value = True
    mock_client.is_daemon_running.return_value = (True, "ok")
    mock_client.is_compose_v2_available.return_value = (True, "v2.20.0")
    mock_client.get_compose_containers.return_value = [
        {
            "Service": "frontend",
            "Name": "opik-opik-frontend-1",
            "State": "running",
            "Health": "healthy",
            "Status": "Up 2 hours",
        }
    ]

    orchestrator = StandaloneOrchestrator(docker_client=mock_client)
    code = orchestrator.status()
    assert code == 0


# ============================================================================
# 6. CLI Standalone Invocation Tests
# ============================================================================


def test_cli_standalone_mode_routing(monkeypatch):
    """Verify CLI lifecycle commands invoke StandaloneOrchestrator outside repo."""
    runner = CliRunner()
    monkeypatch.setenv("TRAILYTICS_DEPLOYMENT_MODE", "standalone")

    with mock.patch("trailytics.deployment.orchestrator.StandaloneOrchestrator.status", return_value=0) as mock_status:
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        mock_status.assert_called_once()

    with mock.patch("trailytics.deployment.orchestrator.StandaloneOrchestrator.stop", return_value=0) as mock_stop:
        result = runner.invoke(cli, ["stop"])
        assert result.exit_code == 0
        mock_stop.assert_called_once()


def test_cli_doctor_standalone_mode(monkeypatch):
    """Verify trailytics doctor in standalone mode reports standalone assets and mode."""
    runner = CliRunner()
    monkeypatch.setenv("TRAILYTICS_DEPLOYMENT_MODE", "standalone")

    def fake_subprocess_run(cmd, *args, **kwargs):
        if "info" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="info", stderr="")
        if "version" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="v2.27.0", stderr="")
        if "config" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        if "ps" in cmd and "docker" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with mock.patch("subprocess.run", side_effect=fake_subprocess_run):
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "Trailytics Doctor (Mode: Standalone)" in result.output
        assert "Standalone (Packaged Distribution)" in result.output
        assert "Bundled deployment assets" in result.output
