#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_config
require_docker
verify_upstream
verify_deployment_identity

COMPOSE_FILE="$UPSTREAM_DIR/deployment/docker-compose/docker-compose.yaml"

# Construct the docker compose logs command
# We use the verified project identity $TRAILYTICS_COMPOSE_PROJECT and the compose file.
# Profile opik includes all standard Opik services.
exec docker compose -p "$TRAILYTICS_COMPOSE_PROJECT" -f "$COMPOSE_FILE" --profile opik logs "$@"
