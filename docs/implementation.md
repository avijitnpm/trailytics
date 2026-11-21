# Trailytics Phase 1 implementation notes

The frontend patch is intentionally limited to the browser title, favicon,
sidebar wordmark, onboarding greeting, Development sidebar group, GitHub-stars
control, and Support submenu. Routes and all backend capabilities remain
upstream.

The wrapper uses Opik's existing `OPIK_MAX_STARTUP_RETRIES` validation and sets
it to 600 seconds, matching the pinned backend health-check allowance. The
frontend remains gated by the upstream Compose health dependency; no health
checks or Compose dependencies are weakened.

The build process tags the local patched image with the image reference used by
the upstream Compose file and sets `OPIK_FRONTEND_PULL_POLICY=never`; therefore
the upstream launcher remains unchanged and cannot replace the patched image.
