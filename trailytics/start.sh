#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_config
require_docker
verify_upstream
verify_deployment_identity
if needs_frontend_build; then
  "$SCRIPT_DIR/build-frontend.sh"
fi

attempt=1
while :; do
  if run_upstream; then
    echo "Trailytics is ready at $(dashboard_url)"
    exit 0
  fi
  echo "Trailytics: startup attempt $attempt/$TRAILYTICS_STARTUP_ATTEMPTS did not become healthy within ${TRAILYTICS_STARTUP_TIMEOUT_SECONDS}s." >&2
  print_startup_diagnostics
  if [ "$attempt" -ge "$TRAILYTICS_STARTUP_ATTEMPTS" ]; then
    fail "startup failed after $attempt attempt(s); containers and volumes were left in place (see diagnostics above)"
  fi
  attempt=$((attempt + 1))
  echo "Trailytics: retrying startup (attempt $attempt/$TRAILYTICS_STARTUP_ATTEMPTS) in ${TRAILYTICS_STARTUP_RETRY_DELAY_SECONDS}s..." >&2
  sleep "$TRAILYTICS_STARTUP_RETRY_DELAY_SECONDS"
done
