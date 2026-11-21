# Trailytics Phase 1 implementation notes

## Frontend patch

The patch is applied to a temporary copy of the pinned Opik frontend, never to
`upstream/opik`. It changes visible product identity only: browser title,
favicon, sidebar wordmark, Support submenu, GitHub-stars control, Development
sidebar group, and product-facing copy in onboarding, the welcome wizard, the
pairing screen, OAuth consent, agent setup, the agent-runner empty state, the
user menu, mobile onboarding, and the trace-limit screen. Routes, APIs, SDKs,
backend services, and internal identifiers remain upstream.

The build applies every `frontend/patches/*.patch` with
`patch --forward --batch`, so a patch whose context no longer matches the pinned
source fails the build instead of being silently skipped.

## Deployment identity

The upstream launcher derives the Compose project name from the directory of the
`upstream/opik` submodule and computes host-port offsets from a hash of the
checkout path. Because the submodule directory is always `upstream/opik`, the
project name is stable (`opik-opik`) across clone locations, while only
cosmetic ports not used by the Compose deployment are offset. The wrapper
asserts the project name before acting and refuses to touch a project that
contains containers started from another checkout.

The project name is intentionally not renamed: the current database lives in
the `opik-opik_*` volumes, and Compose would attach a renamed project to a new,
empty volume set.

## Startup

The wrapper passes `OPIK_MAX_STARTUP_RETRIES=600`, matching the pinned backend
health-check allowance. The frontend remains gated by the upstream Compose
health dependency; no health checks or Compose dependencies are weakened.
`start.sh` retries the launcher (`TRAILYTICS_STARTUP_ATTEMPTS`) and prints
per-container status plus log tails for unhealthy services on each failed
attempt. It never starts a second Compose project and never removes volumes.

## Image substitution and rebuilds

The build tags the local patched image with the image reference used by the
upstream Compose file and sets `OPIK_FRONTEND_PULL_POLICY=never`, so the
untouched Compose file cannot replace the patched image with the upstream one.

Each image carries an `io.trailytics.build-fingerprint` label computed from the
pinned Opik version/commit plus the contents of `frontend/patches` and
`frontend/assets`. `start.sh` rebuilds only when that fingerprint or the pinned
image tag no longer matches, so patch changes are never silently ignored.

## Demo data and telemetry

`CREATE_DEMO_DATA` is the only demo-data switch the pinned Compose deployment
honours; `TOGGLE_DEMO_DATA_ENABLED` is not forwarded to the backend container
and is not used. Upstream install reporting is disabled with
`OPIK_USAGE_REPORT_ENABLED=false`.
