#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="$ROOT_DIR/upstream/opik"
CONFIG_FILE="$ROOT_DIR/config/trailytics.env"

fail() { echo "Trailytics: $*" >&2; exit 1; }
load_config() { test -f "$CONFIG_FILE" || fail "missing $CONFIG_FILE"; set -a; source "$CONFIG_FILE"; set +a; }
require_docker() { command -v docker >/dev/null || fail "Docker is required. Install Docker and try again."; docker info >/dev/null 2>&1 || fail "Docker is not running or is not accessible."; docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."; }
verify_upstream() { test -e "$UPSTREAM_DIR/.git" || fail "Opik submodule is not initialized. Run ./trailytics/install.sh."; test "$(git -C "$UPSTREAM_DIR" rev-parse HEAD)" = "$OPIK_COMMIT" || fail "upstream Opik commit does not match the pinned $OPIK_VERSION release"; test -z "$(git -C "$UPSTREAM_DIR" status --porcelain)" || fail "upstream Opik has local modifications; refusing to build from a non-reproducible baseline"; }
image_present() { docker image inspect "$TRAILYTICS_FRONTEND_IMAGE" >/dev/null 2>&1; }
run_upstream() { (cd "$UPSTREAM_DIR" && OPIK_VERSION="$OPIK_VERSION" OPIK_FRONTEND_PULL_POLICY="$OPIK_FRONTEND_PULL_POLICY" NGINX_PORT="$TRAILYTICS_DASHBOARD_PORT" CREATE_DEMO_DATA="$CREATE_DEMO_DATA" TOGGLE_DEMO_DATA_ENABLED="$TOGGLE_DEMO_DATA_ENABLED" OPIK_MAX_STARTUP_RETRIES="$TRAILYTICS_STARTUP_TIMEOUT_SECONDS" ./opik.sh "$@"); }
dashboard_url() { echo "http://localhost:${TRAILYTICS_DASHBOARD_PORT}"; }
