# Trailytics

Trailytics is a simplified self-hosted AI observability interface built on the
[Opik](https://github.com/comet-ml/opik) open-source engine. It keeps Opik's
backend, APIs, SDKs, storage, tracing, and evaluation capabilities intact while
providing a focused product surface for observability and evaluation.

## Prerequisites

Before running Trailytics, ensure the following prerequisites are installed on your machine:

- **Docker** (daemon running and accessible to current user)
- **Docker Compose v2** (`docker compose version` $\ge 2.20$)
- **Python 3.10+** (tested through Python 3.14)
- **Git** with submodule support (only required for Development Mode from source)

## Quick Start (Standalone Mode)

Install Trailytics directly via `pip` without cloning the repository:

```bash
pip install trailytics

# Start the observability platform
trailytics start

# Check container health and status
trailytics status

# View and follow runtime logs
trailytics logs -f

# Run comprehensive system diagnostics
trailytics doctor

# Stop containers safely (preserves persistent volumes and data)
trailytics stop
```

Once started, open the web dashboard in your browser:
**[http://localhost:5173](http://localhost:5173)**

## Dual-Mode Architecture

Trailytics CLI provides seamless dual-mode execution:

1. **Standalone Mode (Packaged Distribution):**
   - Active when Trailytics is installed via `pip` outside a Git repository checkout.
   - Uses bundled deployment manifests (`docker-compose.yaml`, ClickHouse configurations, and Nginx reverse proxy templates) packaged directly inside the Python distribution.
   - Executes Docker Compose commands natively using direct Python subprocess execution with project identity `opik-opik`.
   - Resolves frontend images with automatic multi-tier fallback:
     1. Local image cache (`trailytics-frontend:2.2.138`)
     2. Docker Hub branded registry (`avijitnpm/trailytics-frontend:2.2.138`)
     3. Upstream fallback (`ghcr.io/comet-ml/opik/opik-frontend:2.2.138`) with clear warning notice.

2. **Development Mode (Repository Checkout):**
   - Active when running from within the Trailytics Git repository.
   - Preserves developer workflows by delegating to repository shell scripts (`trailytics/start.sh`, `trailytics/stop.sh`, `trailytics/status.sh`, `trailytics/logs.sh`, `trailytics/doctor.sh`).
   - Supports local frontend image building via `trailytics/build-frontend.sh`.

You can force standalone mode in development by setting `TRAILYTICS_DEPLOYMENT_MODE=standalone`.

## Development Installation (From Source)

To develop Trailytics or build frontend customizations locally:

```bash
git clone --recurse-submodules <your-trailytics-repository>
cd trailytics
./trailytics/install.sh
```

The `upstream/opik` submodule is fetched with its full history: the pinned
release is identified by commit, not by the tip of a branch, so a shallow
`--depth 1` fetch is not safe on a fresh machine.

### Development Lifecycle Scripts

When working inside the repository checkout:

```bash
./trailytics/start.sh
./trailytics/status.sh
./trailytics/logs.sh
./trailytics/doctor.sh
./trailytics/stop.sh
```

`stop.sh` (and `trailytics stop`) uses non-destructive operations. It never removes
Docker volumes, databases, traces, projects, or other persistent user data.

## Deployment Identity & Volume Safety

Trailytics strictly runs under one Docker Compose project: `opik-opik`.
This ensures that whether you run via CLI standalone mode or development shell scripts, both environments bind to the exact same persistent Docker volumes:

- `opik-opik_mysql`: Relational metadata and user accounts.
- `opik-opik_clickhouse`: High-throughput trace and span data.
- `opik-opik_minio-data`: S3-compatible artifact storage.
- `opik-opik_redis-data`: Cache and messaging state.

**Persistent data is never removed during standard lifecycle operations (`stop`, `restart`, `start`).** Trailytics never executes `docker compose down -v`.

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

### Viewing Traces

Once traces are logged and flushed:

1. Open the Trailytics dashboard in your browser: [http://localhost:5173](http://localhost:5173).
2. Select your project (e.g. `My Project` or `Default Project`).
3. Inspect trace timelines, inputs, outputs, execution duration, and nested span calls.

### Configuration & Privacy

* `TRAILYTICS_URL`: Defaults to `http://localhost:5173/api/` (maps to `OPIK_URL_OVERRIDE`).
* `TRAILYTICS_PROJECT`: Defaults to `Default Project` (maps to `OPIK_PROJECT_NAME`).
* `TRAILYTICS_WORKSPACE`: Defaults to `default` (maps to `OPIK_WORKSPACE`).
* External Comet analytics (`OPIK_ANALYTICS_ENABLE`) and external Sentry error reporting (`OPIK_SENTRY_ENABLE`) are disabled by default.

## Trailytics CLI (Phase 3)

Trailytics includes a developer-facing command-line interface. The CLI delegates deployment operations directly to the verified shell lifecycle scripts, preserving all safety guarantees and persistent data:

```bash
trailytics --help
trailytics start       # Start deployment and verify services (delegates to trailytics/start.sh)
trailytics status      # Check health of runtime containers (delegates to trailytics/status.sh)
trailytics logs        # View and stream container logs (delegates to trailytics/logs.sh)
trailytics doctor      # Run comprehensive read-only diagnostics across repo, Docker, and services
trailytics stop        # Stop containers safely without deleting volumes (delegates to trailytics/stop.sh)
trailytics restart     # Safely stop then start deployment
trailytics version     # Show Trailytics, Opik engine, and commit metadata
```

### Viewing Logs

```bash
trailytics logs                         # View last 100 lines across all services
trailytics logs --follow                # Follow logs continuously (Ctrl+C to exit)
trailytics logs --tail 200 backend      # View last 200 lines from backend service
trailytics logs -f frontend backend     # Follow logs from frontend and backend
```

### Running Diagnostics

`trailytics doctor` performs non-mutating, read-only diagnostics across repository integrity, Docker environment, deployment identity, and HTTP connectivity. It never modifies or repairs the deployment automatically.

```bash
trailytics doctor
```

Example `trailytics version` output:

```text
Trailytics  0.3.0
Opik Engine 2.2.138
Commit      28192d8ffe85299f5c44032f705a9e518e6d1189
```

## Profile Management & Configuration

Trailytics supports named connection profiles to manage different local and remote environments (e.g., local, staging, production).

### Profile Commands

```bash
# List all configured profiles
trailytics profile list

# Create a new profile (prompts securely for API key)
trailytics profile create production \
  --type remote \
  --url https://trailytics.company.com/api \
  --workspace production-ai \
  --project "Main App"

# Create a profile without entering an API key
trailytics profile create staging \
  --url https://staging.company.com/api \
  --no-api-key

# Inspect a profile configuration and credential status
trailytics profile show production

# Switch the default profile
trailytics profile use production

# Delete a profile (and its associated stored credentials)
trailytics profile delete staging -y
```

### Profile Selection

- **Command-line option:** Override the profile for a single command:
  ```bash
  trailytics --profile staging doctor
  ```
- **Environment variable:** Override the profile in your shell session:
  ```bash
  export TRAILYTICS_PROFILE=production
  ```
- **Persistent default:** Configured in `~/.trailytics/config.toml` via `trailytics profile use <name>`.

### Credential Storage & Security

- **Configuration:** Saved in `~/.trailytics/config.toml` (non-sensitive profile metadata).
- **Credentials:** API keys are stored separately in `~/.trailytics/credentials.toml` with strict `0600` POSIX permissions (owner read/write only).
- API keys are never stored in `config.toml`, never accepted as command-line arguments, and never displayed in `profile list` or `profile show`.

### Configuration Precedence

1. CLI command-line options
2. Environment variables (`TRAILYTICS_URL`, `TRAILYTICS_API_KEY`, `TRAILYTICS_WORKSPACE`, `TRAILYTICS_PROJECT`)
3. Selected profile configuration
4. Built-in defaults (`http://localhost:5173/api`, workspace `default`)

## Known Limitations

- **Local Docker Engine:** Requires a local Docker daemon and Docker Compose v2. Remote SSH host targets or Kubernetes deployments are not managed locally by Docker Compose.
- **Single-Node Stack:** The Compose topology is designed for single-node development and team server deployments under project identity `opik-opik`.
- **Pinned Upstream Engine:** Built and verified specifically against Opik `2.2.138` (commit `28192d8ffe85299f5c44032f705a9e518e6d1189`). Arbitrary upstream branch updates are not automatically applied.

## Upstream and reproducibility

This distribution pins Opik `2.2.138` at
`28192d8ffe85299f5c44032f705a9e518e6d1189`. The `upstream/opik` Git submodule
is never edited. Trailytics applies its frontend patch only to a temporary,
ignored build context. Opik license and attribution files remain in the
submodule and apply to the upstream engine.
