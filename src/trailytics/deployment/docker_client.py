"""Subprocess wrapper for Docker and Docker Compose commands."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class DockerClient:
    """Encapsulates system Docker CLI interactions without external dependencies."""

    def __init__(self, docker_path: Optional[str] = None) -> None:
        self.docker_cmd = docker_path or shutil.which("docker") or "docker"

    def is_docker_installed(self) -> bool:
        """Check if docker CLI executable is present in PATH."""
        return shutil.which(self.docker_cmd) is not None

    def is_daemon_running(self) -> Tuple[bool, str]:
        """Check if Docker daemon is running and reachable."""
        if not self.is_docker_installed():
            return False, "Docker executable is not installed or not found in PATH."
        try:
            res = subprocess.run(
                [self.docker_cmd, "info"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                return True, "Docker daemon is active and accessible."
            err_msg = res.stderr.strip() or "Docker daemon returned a non-zero exit code."
            return False, err_msg
        except OSError as e:
            return False, f"Failed to execute docker info: {e}"

    def is_compose_v2_available(self) -> Tuple[bool, str]:
        """Verify Docker Compose v2 is available via 'docker compose'."""
        if not self.is_docker_installed():
            return False, "Docker is not installed."
        try:
            res = subprocess.run(
                [self.docker_cmd, "compose", "version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                version_str = res.stdout.strip()
                return True, version_str
            return False, res.stderr.strip() or "Docker Compose v2 is not available."
        except OSError as e:
            return False, f"Failed to execute docker compose version: {e}"

    def image_exists_locally(self, image_ref: str) -> bool:
        """Check if a container image exists in the local Docker image cache."""
        try:
            res = subprocess.run(
                [self.docker_cmd, "image", "inspect", image_ref],
                capture_output=True,
                text=True,
                check=False,
            )
            return res.returncode == 0
        except OSError:
            return False

    def try_pull_image(self, image_ref: str) -> bool:
        """Attempt to pull a container image from a remote registry."""
        try:
            res = subprocess.run(
                [self.docker_cmd, "pull", image_ref],
                capture_output=True,
                text=True,
                check=False,
            )
            return res.returncode == 0
        except OSError:
            return False

    def is_port_in_use(self, port: int, host: str = "127.0.0.1") -> bool:
        """Check if a local TCP port is already in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                res = s.connect_ex((host, port))
                return res == 0
            except OSError:
                return False

    def get_compose_containers(self, project: str) -> List[Dict[str, Any]]:
        """Get structured list of container statuses for a Compose project."""
        try:
            res = subprocess.run(
                [self.docker_cmd, "compose", "-p", project, "ps", "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                return []
            containers: List[Dict[str, Any]] = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if line:
                    try:
                        containers.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return containers
        except OSError:
            return []

    def get_container_logs(self, container_name: str, tail: int = 40) -> str:
        """Get last N lines of logs from a specific container."""
        try:
            res = subprocess.run(
                [self.docker_cmd, "logs", "--tail", str(tail), container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            return (res.stdout + res.stderr).strip()
        except OSError:
            return ""

    def run_compose(
        self,
        project: str,
        compose_file: Path,
        compose_args: List[str],
        env: Optional[Dict[str, str]] = None,
        capture_output: bool = False,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Execute a docker compose command with explicit project and manifest flags."""
        cmd = [
            self.docker_cmd,
            "compose",
            "-p",
            project,
            "-f",
            str(compose_file),
        ] + compose_args

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        return subprocess.run(
            cmd,
            env=merged_env,
            capture_output=capture_output,
            text=True,
            check=check,
        )

    def stream_compose(
        self,
        project: str,
        compose_file: Path,
        compose_args: List[str],
        env: Optional[Dict[str, str]] = None,
    ) -> int:
        """Execute a docker compose command, streaming stdout/stderr to the terminal."""
        cmd = [
            self.docker_cmd,
            "compose",
            "-p",
            project,
            "-f",
            str(compose_file),
        ] + compose_args

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        proc = subprocess.Popen(cmd, env=merged_env)
        try:
            return proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            return 130
