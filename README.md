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

## Daily commands

```bash
./trailytics/start.sh
./trailytics/status.sh
./trailytics/stop.sh
```

`stop.sh` uses the upstream non-destructive stop command. It does not remove
Docker volumes, databases, traces, projects, or other persistent user data.

## Upstream and reproducibility

This distribution pins Opik `2.2.138` at
`28192d8ffe85299f5c44032f705a9e518e6d1189`. The `upstream/opik` Git submodule
is never edited. Trailytics applies its frontend patch only to a temporary,
ignored build context. Opik license and attribution files remain in the
submodule and apply to the upstream engine.

Automatic demo data is disabled for new deployments. To deliberately enable it,
set `CREATE_DEMO_DATA=true` and `TOGGLE_DEMO_DATA_ENABLED=true` in
`config/trailytics.env` before startup. This does not remove any existing data.
