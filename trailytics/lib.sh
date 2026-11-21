#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="$ROOT_DIR/upstream/opik"
CONFIG_FILE="$ROOT_DIR/config/trailytics.env"

fail() { echo "Trailytics: $*" >&2; exit 1; }
load_config() { test -f "$CONFIG_FILE" || fail "missing $CONFIG_FILE"; set -a; source "$CONFIG_FILE"; set +a; }
require_docker() { command -v docker >/dev/null || fail "Docker is required. Install Docker and try again."; docker info >/dev/null 2>&1 || fail "Docker is not running or is not accessible."; docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."; }
verify_upstream() { test -e "$UPSTREAM_DIR/.git" || fail "Opik submodule is not initialized. Run ./trailytics/install.sh."; test "$(git -C "$UPSTREAM_DIR" rev-parse HEAD)" = "$OPIK_COMMIT" || fail "upstream Opik commit does not match the pinned $OPIK_VERSION release"; test -z "$(git -C "$UPSTREAM_DIR" status --porcelain)" || fail "upstream Opik has local modifications; refusing to build from a non-reproducible baseline"; }

# The upstream launcher (upstream/opik/scripts/worktree-utils.sh) derives the
# Compose project as "opik-<basename of the git toplevel of upstream/opik>".
# upstream/opik is a submodule, so that toplevel is always the submodule
# directory and the value does not depend on where the repository was cloned.
upstream_compose_project() {
  local toplevel name
  toplevel="$(git -C "$UPSTREAM_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$toplevel" ] || toplevel="$UPSTREAM_DIR"
  name="$(basename "$toplevel" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g; s/--*/-/g; s/^-//; s/-$//')"
  printf 'opik-%s\n' "${name:-default}"
}

# Refuse to operate on a Compose project that also holds containers started
# from another checkout (for example an unrelated Opik clone that happens to
# resolve to the same project name). Trailytics must never stop or reconfigure
# somebody else's deployment. Compose records the directory of the Compose file
# as the working dir, which is the upstream deployment directory here.
verify_deployment_identity() {
  local project foreign
  project="$(upstream_compose_project)"
  [ "$project" = "$TRAILYTICS_COMPOSE_PROJECT" ] || fail "this checkout resolves to Docker project '$project', not the expected '$TRAILYTICS_COMPOSE_PROJECT'; refusing to touch a different deployment"
  foreign="$(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Label "com.docker.compose.project.working_dir"}}' | grep -v -x -e '' -e "$UPSTREAM_DIR" -e "$UPSTREAM_DIR/deployment/docker-compose" | sort -u || true)"
  [ -z "$foreign" ] || fail "Docker project '$project' also contains containers from: $foreign. Refusing to modify another deployment."
}

# Deterministic fingerprint of every input that can change the built frontend.
# Paths are hashed relative to the repository root so moving the checkout does
# not invalidate a perfectly good image.
frontend_fingerprint() {
  ( cd "$ROOT_DIR" && {
      printf 'opik_version=%s\nopik_commit=%s\n' "$OPIK_VERSION" "$OPIK_COMMIT"
      find frontend/patches frontend/assets -type f -print | LC_ALL=C sort | xargs -r sha256sum
    } ) | sha256sum | cut -d' ' -f1
}

image_present() { docker image inspect "$TRAILYTICS_FRONTEND_IMAGE" >/dev/null 2>&1; }
image_fingerprint() { docker image inspect --format '{{index .Config.Labels "io.trailytics.build-fingerprint"}}' "$TRAILYTICS_FRONTEND_IMAGE" 2>/dev/null || true; }
image_id() { docker image inspect --format '{{.Id}}' "$1" 2>/dev/null || true; }

# 0 = rebuild, 1 = the existing image already matches the current inputs and the
# pinned Opik tag still points at it.
needs_frontend_build() {
  image_present || return 0
  [ "$(image_fingerprint)" = "$(frontend_fingerprint)" ] || return 0
  [ "$(image_id "$TRAILYTICS_FRONTEND_IMAGE")" = "$(image_id "ghcr.io/comet-ml/opik/opik-frontend:$OPIK_VERSION")" ] || return 0
  return 1
}

run_upstream() { (cd "$UPSTREAM_DIR" && OPIK_VERSION="$OPIK_VERSION" OPIK_FRONTEND_PULL_POLICY="$OPIK_FRONTEND_PULL_POLICY" NGINX_PORT="$TRAILYTICS_DASHBOARD_PORT" CREATE_DEMO_DATA="$CREATE_DEMO_DATA" OPIK_USAGE_REPORT_ENABLED="$TRAILYTICS_USAGE_REPORT_ENABLED" OPIK_MAX_STARTUP_RETRIES="$TRAILYTICS_STARTUP_TIMEOUT_SECONDS" ./opik.sh "$@"); }

dashboard_url() { echo "http://localhost:${TRAILYTICS_DASHBOARD_PORT}"; }

print_startup_diagnostics() {
  local project name state
  project="$(upstream_compose_project)"
  echo "Trailytics: diagnostics for Docker project '$project' (working dir $UPSTREAM_DIR)" >&2
  docker ps -a --filter "label=com.docker.compose.project=$project" --format 'table {{.Names}}\t{{.Status}}' >&2 || true
  for name in $(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Names}}'); do
    state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || echo unknown)"
    code="$(docker inspect --format '{{.State.ExitCode}}' "$name" 2>/dev/null || echo 0)"
    case "$state" in
      healthy|running) continue ;;
      exited) if [ "$code" = "0" ]; then continue; fi ;;
    esac
    echo "Trailytics: $name is '$state' (exit code $code); last 40 log lines:" >&2
    docker logs --tail 40 "$name" >&2 2>&1 || true
  done
}
