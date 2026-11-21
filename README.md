# Trailytics

Trailytics is a simplified self-hosted AI observability interface built on the
[Opik](https://github.com/comet-ml/opik) open-source engine. It keeps Opik's
backend, APIs, SDKs, storage, tracing, and evaluation capabilities intact while
providing a focused product surface for observability and evaluation.

## Install

```bash
git clone --recurse-submodules <your-trailytics-repository>
cd trailytics
./trailytics/install.sh
```

Open http://localhost:5173 when installation completes.

The `upstream/opik` submodule is fetched with its full history: the pinned
release is identified by commit, not by the tip of a branch, so a shallow
`--depth 1` fetch is not safe on a fresh machine.

## Daily commands

```bash
./trailytics/start.sh
./trailytics/status.sh
./trailytics/stop.sh
```

`stop.sh` uses the upstream non-destructive stop command. It does not remove
Docker volumes, databases, traces, projects, or other persistent user data.

## Deployment identity

Trailytics runs as one Docker Compose project: `opik-opik`. The upstream
launcher derives the name from the `upstream/opik` submodule directory, so it is
the same no matter where the repository is cloned or which directory a command
is run from. The wrapper scripts assert that identity before doing anything and
refuse to start, stop, or inspect a project that also contains containers from a
different checkout.

Do not rename the project by hand. The existing database lives in the
`opik-opik_*` Docker volumes; changing the project name makes Compose look at a
different, empty set of volumes.

## Older deployments on this machine

Previous checkouts (before the directory was renamed) produced separate stacks
whose names were derived from the old directory names:

- `opik-opik-2-2-138-*` containers and `opik-opik-2-2-138_*` volumes
- `opik-opik-2-2-143-*` containers and `opik-opik-2-2-143_*` volumes

They can be identified with:

```bash
docker ps -a --filter name=opik-opik-2-2-138 --format 'table {{.Names}}\t{{.Status}}'
docker volume ls --filter name=opik-opik-2-2-138
```

Trailytics never reads, migrates, renames, or deletes these resources. If their
data is needed, inspect them deliberately; `stop.sh` only ever targets the
pinned `opik-opik` project.

## Reproducible builds

`build-frontend.sh` fingerprints the frontend patches, branding assets, and the
pinned Opik version/commit, and stores that fingerprint as an image label.
`start.sh` rebuilds the frontend only when the fingerprint no longer matches, so
editing a patch always produces a new image and unchanged inputs do not trigger
a rebuild. `./trailytics/build-frontend.sh --force` rebuilds unconditionally.

## Demo data

Automatic demo data is disabled (`CREATE_DEMO_DATA=false`). To deliberately
enable it, set `CREATE_DEMO_DATA=true` in `config/trailytics.env` before
startup. This does not remove any existing data.

`TOGGLE_DEMO_DATA_ENABLED` is an upstream backend setting that the pinned
Compose deployment does not forward into the backend container, so Trailytics
does not set or document it as a supported switch.

## Telemetry

Upstream Opik sends an anonymous installation report unless
`OPIK_USAGE_REPORT_ENABLED=false`. Trailytics sets
`TRAILYTICS_USAGE_REPORT_ENABLED=false` in `config/trailytics.env` and exports
it to the launcher, so no install report is sent.

## Python SDK (Phase 2)

Trailytics provides a Python package that allows developers to trace applications with a Trailytics-branded interface while delegating underlying tracing, serialization, and batch transport to Opik 2.2.138.

### Installation

For local development within the repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e upstream/opik/sdks/python
pip install -e .
```

### Usage

```python
import trailytics

# Optional: configure project and endpoint (defaults to http://localhost:5173/api/)
trailytics.configure(project_name="My Project")

@trailytics.track
def generate_response(prompt: str) -> dict:
    return {"response": f"Processed: {prompt}"}

result = generate_response("Hello Trailytics")
trailytics.flush()
```

Direct symbol imports are also supported:

```python
from trailytics import track, configure, flush, Client

@track
def process(data):
    return data

result = process("data")
flush()
```

### Configuration & Privacy

* `TRAILYTICS_URL`: Defaults to `http://localhost:5173/api/` (maps to `OPIK_URL_OVERRIDE`).
* `TRAILYTICS_PROJECT`: Defaults to `Default Project` (maps to `OPIK_PROJECT_NAME`).
* `TRAILYTICS_WORKSPACE`: Defaults to `default` (maps to `OPIK_WORKSPACE`).
* External Comet analytics (`OPIK_ANALYTICS_ENABLE`) and external Sentry error reporting (`OPIK_SENTRY_ENABLE`) are disabled by default.

## Upstream and reproducibility

This distribution pins Opik `2.2.138` at
`28192d8ffe85299f5c44032f705a9e518e6d1189`. The `upstream/opik` Git submodule
is never edited. Trailytics applies its frontend patch only to a temporary,
ignored build context. Opik license and attribution files remain in the
submodule and apply to the upstream engine.
