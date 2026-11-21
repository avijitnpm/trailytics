#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_config
require_docker
verify_upstream
verify_deployment_identity
echo "Trailytics dashboard: $(dashboard_url)"
run_upstream --verify
