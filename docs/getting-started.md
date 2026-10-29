# Getting started

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — manages the Python 3.12 toolchain and
  the workspace. uv downloads Python 3.12 for you.
- **GNU make**
- **Docker Engine + Compose v2** — for the compose stack (`docker compose version`).

## Bootstrap and run

```sh
make bootstrap    # prerequisites, .env (with generated secrets), uv sync, pull images
make up           # start core infra, wait until healthy
make test         # unit tests (no docker/network)
```

On a machine without Docker you can still work on the Python workspace:

```sh
SKIP_DOCKER=1 make bootstrap
make test
make lint
make typecheck
```

## What comes up in M0

Only the core infrastructure: Keycloak, PostgreSQL, NATS JetStream, and step-ca
(see the service/port table in the top-level [`README.md`](../README.md)). Only
Keycloak is host-exposed (on `127.0.0.1`); the others are reached via
`docker compose exec`. The application services arrive in later milestones.

## Configuration

Set `AGENTBANK_PROJECT` (default `agentbank`) to change the Docker Compose
project name, so several checkouts can run side by side on one host without
colliding containers, networks or volumes:

```sh
AGENTBANK_PROJECT=agentbank-pr42 make up
```

The Makefile exports it, so the helper scripts invoked by `make health`,
`make pki-root` and `make test-compose` all use the same project name.

## Useful targets

| Command | What it does |
|---|---|
| `make ps` / `make logs` / `make health` | Inspect the running stack |
| `make pki-root` | Export the step-ca root cert to `deploy/pki/out/` (stack must be up) |
| `make test-compose` | Live checks against the running stack |
| `make check` | lint + typecheck + test |
| `make compose-config` | Validate all compose files |
| `make down` | Stop the stack |

Run `make help` for the full list.
