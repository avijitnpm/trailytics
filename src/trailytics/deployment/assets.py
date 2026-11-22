"""Asset location and verification for bundled Trailytics deployment manifests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

if sys.version_info >= (3, 9):
    from importlib import resources
else:  # pragma: no cover
    import importlib_resources as resources  # type: ignore


def get_deployment_dir() -> Path:
    """Return the absolute filesystem path to the bundled deployment directory."""
    # resources.files() returns a Traversable, convert str to Path
    traversable = resources.files("trailytics.deployment")
    return Path(str(traversable)).resolve()


def get_compose_file_path() -> Path:
    """Return the absolute path to the bundled docker-compose.yaml file."""
    return get_deployment_dir() / "docker-compose.yaml"


def get_nginx_config_path() -> Path:
    """Return the absolute path to the bundled nginx_default_local.conf file."""
    return get_deployment_dir() / "nginx_default_local.conf"


def get_clickhouse_config_dir() -> Path:
    """Return the absolute path to the bundled clickhouse_config directory."""
    return get_deployment_dir() / "clickhouse_config"


def verify_deployment_assets() -> List[str]:
    """Verify all required standalone deployment assets exist on disk.

    Returns:
        List of missing asset descriptions (empty if all exist).
    """
    missing: List[str] = []

    compose_file = get_compose_file_path()
    if not compose_file.is_file():
        missing.append(f"Missing Compose manifest: {compose_file}")

    nginx_conf = get_nginx_config_path()
    if not nginx_conf.is_file():
        missing.append(f"Missing Nginx config: {nginx_conf}")

    ch_dir = get_clickhouse_config_dir()
    required_ch_files = [
        ch_dir / "additional_config.xml",
        ch_dir / "users.d" / "distributed_insert_queue.xml",
        ch_dir / "users.d" / "enable_time_type.xml",
    ]
    for ch_file in required_ch_files:
        if not ch_file.is_file():
            missing.append(f"Missing ClickHouse config: {ch_file}")

    return missing
