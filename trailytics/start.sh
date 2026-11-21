#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_config
require_docker
verify_upstream
image_present || "$SCRIPT_DIR/build-frontend.sh"

if ! run_upstream; then
  echo "Trailytics: startup did not become healthy within ${TRAILYTICS_STARTUP_TIMEOUT_SECONDS}s." >&2
  run_upstream --verify || true
  docker ps --format 'table {{.Names}}\t{{.Status}}' >&2 || true
  exit 1
fi
echo "Trailytics is ready at $(dashboard_url)"
