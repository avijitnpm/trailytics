#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Run doctor via Trailytics CLI
if [ -x "$ROOT_DIR/.venv/bin/trailytics" ]; then
  exec "$ROOT_DIR/.venv/bin/trailytics" doctor "$@"
elif command -v trailytics >/dev/null 2>&1; then
  exec trailytics doctor "$@"
else
  exec python3 -m trailytics.cli doctor "$@"
fi
