#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_config
require_docker
if [ ! -e "$UPSTREAM_DIR/.git" ]; then
  git -C "$ROOT_DIR" submodule update --init --depth 1 upstream/opik
fi
verify_upstream
"$SCRIPT_DIR/build-frontend.sh"
exec "$SCRIPT_DIR/start.sh"
