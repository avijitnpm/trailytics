# Trailytics Phase 1 — Current Status

Updated: 2026-11-21

## Implemented and verified

- Outer repository committed; `upstream/opik` is a real submodule pinned at
  `28192d8ffe85299f5c44032f705a9e518e6d1189`.
- `install.sh` fetches the submodule with full history (no `--depth 1`), so the
  pinned release tag is reachable on a fresh machine.
- Frontend patch extended to 16 files: title, favicon, sidebar wordmark,
  Development group, GitHub stars (workspace and project sidebars), Support
  menu, onboarding integrations,
  welcome wizard, pairing screen, OAuth consent, agent setup, agent-runner
  empty state, user menu, mobile onboarding, trace-limit message.
- Production frontend image built and running; `curl` reports
  `<title>Trailytics</title>` and the served bundle contains the new copy.
- Build fingerprint (`frontend/patches` + assets + pinned version/commit) is
  stored as an image label; `start.sh` rebuilds only when it changes.
- Compose identity asserted as `opik-opik`; start/stop/status refuse a project
  containing containers from another checkout.
- `stop.sh` → `start.sh` cycle preserved the exact same `opik-opik_*` volumes
  (same creation timestamps); MySQL `workspaces` count unchanged.
- Demo data remains off (`CREATE_DEMO_DATA=false`); the generator exits without
  creating data.
- Install telemetry disabled: `send_install_report` with
  `OPIK_USAGE_REPORT_ENABLED=false` returns before any HTTP call (verified with
  a fake `curl`; 0 invocations).
- Startup diagnostics print project status and the log tail of unhealthy or
  failed containers (verified against a stopped frontend).

## Verification limitations

- The fresh-clone test cloned the outer repository locally and resolved the
  submodule URL against the local Opik object store rather than downloading
  from GitHub. `git ls-remote` confirms tag `2.2.138` is exactly the pinned
  commit, so a full GitHub clone can resolve it.
- The retry loop's failure branch was not forced end-to-end: a 1-second budget
  still observed the stack become healthy. Diagnostics were tested directly on
  a stopped container instead.
- The project-level page screenshot timed out in headless Chromium; the
  workspace screenshot verifies the wordmark, title, welcome wizard, and
  "Skip and go to Trailytics".
- Orphaned `opik-opik-2-2-138-*` and `opik-opik-2-2-143-*` stacks and volumes
  were left untouched by design; see README for identification commands.
