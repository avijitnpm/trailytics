#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_config
verify_upstream
require_docker

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1
fingerprint="$(frontend_fingerprint)"

if [ "$FORCE" -eq 0 ] && ! needs_frontend_build; then
  echo "Frontend image $TRAILYTICS_FRONTEND_IMAGE is current (build fingerprint $fingerprint)."
  # Re-point the tag Compose uses in case it was overwritten by a pull.
  docker tag "$TRAILYTICS_FRONTEND_IMAGE" "ghcr.io/comet-ml/opik/opik-frontend:$OPIK_VERSION"
  exit 0
fi

BUILD_DIR="$ROOT_DIR/.trailytics-build/frontend"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cp -a "$UPSTREAM_DIR/apps/opik-frontend/." "$BUILD_DIR/"
for patch in "$ROOT_DIR"/frontend/patches/*.patch; do
  patch -d "$BUILD_DIR" -p1 --forward --batch < "$patch" || fail "could not apply $(basename "$patch") to Opik $OPIK_VERSION"
done
cp "$ROOT_DIR/frontend/assets/trailytics-favicon.svg" "$BUILD_DIR/public/trailytics-favicon.svg"
docker build --build-arg "OPIK_VERSION=$OPIK_VERSION" --label "io.trailytics.build-fingerprint=$fingerprint" -t "$TRAILYTICS_FRONTEND_IMAGE" "$BUILD_DIR"
# Upstream Compose addresses this image by the pinned Opik version. Keep its Compose file untouched.
docker tag "$TRAILYTICS_FRONTEND_IMAGE" "ghcr.io/comet-ml/opik/opik-frontend:$OPIK_VERSION"
echo "Built $TRAILYTICS_FRONTEND_IMAGE for Opik $OPIK_VERSION (build fingerprint $fingerprint)."
