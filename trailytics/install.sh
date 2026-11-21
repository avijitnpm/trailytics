#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_config
require_docker
if [ ! -e "$UPSTREAM_DIR/.git" ]; then
  # Full history: the pinned commit is a release tag, not necessarily the tip of
  # the default branch, so a shallow (--depth 1) fetch cannot be relied on.
  git -C "$ROOT_DIR" submodule update --init upstream/opik
fi
verify_upstream
"$SCRIPT_DIR/build-frontend.sh"
exec "$SCRIPT_DIR/start.sh"
