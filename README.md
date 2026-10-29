# AgentBank-Sec Testbed

A fully simulated, reproducible **US-style open-banking + instant-payments ecosystem** — 3 banks, 3 PSPs/third-party providers, and 1 instant-payment switch ("SimNow") — in which LLM agents operate with real tool access, so researchers can measure **prompt-injection and agent-security attacks and defenses** against ground-truth state oracles.

See [`SPEC.md`](SPEC.md) for the full design.

**Status:** milestones **M0 (skeleton)** and **M1 (ISO 20022 library)** are complete. The uv workspace, core libraries, CI, and a docker compose core stack (Postgres, NATS, Keycloak, step-ca) come up healthy; `make iso-setup` fetches the ISO 20022 XSDs and generates the bindings; `make test` passes, including the Hypothesis round-trip (1,000 cases per §6.1 message). Milestones **M2–M8 are pending** (see [Milestone status](#milestone-status)). The open-banking API is **FDX-inspired, not FDX-certified** (SPEC §1.1), and the whole system is **simulation only**.

> ⚠️ **Safety — everything here is simulated.** No real money, no real bank/PSP/FedNow/RTP endpoints, no real customer data. Routing numbers are fictitious (`9999000xx`), e-mail domains are `.test`. Network egress from the simulation is disabled by default (only an optional, explicit LLM-API egress allow-list). Attack payloads target this testbed only. See [`SAFETY.md`](SAFETY.md).

## Architecture (summary)

Three `bank-core` services (Aurora National, Birchwood Community, Cascade CU), three `psp-core` services (LedgerLink aggregator, PayPath payment initiator, Penny agentic PFM), and the SimNow switch exchange **FDX-inspired** REST traffic over **FAPI 2.0** and **ISO 20022** messages over **NATS JetStream**. Identity is **Keycloak**; internal PKI is **step-ca**; bank cores persist to **PostgreSQL** (schema per bank) with **pgvector**. LLM agents (LangGraph primary) call tools through **MCP servers** behind an **agent-gateway** that applies pluggable defenses. Ground-truth **oracles** read post-run ledger/switch/mail state. The full topology, flows and component specs are in [`SPEC.md`](SPEC.md) §4–§5.

## Prerequisites

- **Docker Engine + Compose v2** (`docker compose version`)
- **GNU make**
- **[uv](https://docs.astral.sh/uv/)** (Python package/workspace manager; it manages Python 3.12 itself)

## Quickstart

```sh
make bootstrap    # check prerequisites, create .env (with generated secrets), uv sync, pull images
make up           # start core infra (Postgres, NATS, Keycloak, step-ca) and wait for healthy
make test         # run the unit test suite
```

`make help` lists all targets. Run `make down` to stop the stack.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `AGENTBANK_PROJECT` | `agentbank` | Docker Compose project name. Override it to run several checkouts side by side on one host without their containers, networks or volumes colliding. |
| `SKIP_DOCKER` | `0` | Set to `1` so `make bootstrap` skips all docker steps (for machines without docker, e.g. the lint-only CI job). |

```sh
AGENTBANK_PROJECT=agentbank-pr42 make up   # isolated stack for this checkout
```

The Makefile exports `AGENTBANK_PROJECT` so the helper scripts (`make health`,
`make pki-root`, …) use the same project name.

## Services and ports (M0 core infra)

Per SPEC §15, `bank-net`/`switch-net`/`agent-net` are `internal`, and a container
on only internal networks cannot publish host ports. So in M0 **only Keycloak**
(on the `edge` network) is host-exposed; Postgres, NATS and step-ca are reached
via `docker compose exec` (see `make health` / `make test-compose`). Every host
port binds to `127.0.0.1` only.

| Service | Image | Networks | Host port(s) | Health |
|---|---|---|---|---|
| Keycloak | `quay.io/keycloak/keycloak:26.4` | edge, bank-net | `8080` (HTTP), `9000` (management) | `/health/ready` on `9000` → `UP` |
| PostgreSQL | `pgvector/pgvector:pg16` | bank-net | — (exec) | `pg_isready` |
| NATS JetStream | `nats:2.11-alpine` | switch-net | — (exec) | `http://localhost:8222/healthz` |
| step-ca | `smallstep/step-ca:0.28.4` | switch-net, bank-net | — (exec) | `step ca health` |

Later milestones add the bank/PSP/switch/agent services and the observability stack (see `deploy/compose.*.yaml`).

## Make targets

| Target | Description |
|---|---|
| `bootstrap` | Check prerequisites, create `.env` (with generated secrets), `uv sync`, pull images |
| `up` | Start core infra and wait until every service is healthy |
| `down` | Stop and remove the stack |
| `ps` | Show compose service status |
| `logs` | Tail compose logs |
| `health` | Print the health of each service |
| `pki-root` | Export the step-ca root cert to `deploy/pki/out/` (stack must be up) |
| `test` | Run unit tests (no docker/network; needs `make iso-setup` once) |
| `test-iso` | ISO 20022 acceptance tests, with Hypothesis statistics |
| `test-compose` | Live checks against the running stack (docker required) |
| `iso-setup` | Download and SHA-256-verify the ISO XSDs, then generate bindings |
| `iso-gen` | Regenerate xsdata bindings from the local XSDs |
| `xsd-install` | Download missing XSDs from iso20022.org and verify SHA-256 |
| `xsd-verify` | Offline: recompute SHA-256 of the local XSDs against the manifest |
| `xsd-fetch` | Re-download XSDs to a temp dir and compare hashes only |
| `lint` | `ruff check` + `ruff format --check` |
| `format` | Apply `ruff format` |
| `typecheck` | `mypy` (strict) |
| `check` | `lint` + `typecheck` + `test` |
| `compose-config` | Validate all compose files |
| `clean` | Remove caches and generated artifacts |
| `seed` / `reset` / `bench` / `report` / `controls-check` | Not implemented yet (later milestones) |

## Milestone status

| M | Deliverable | Status |
|---|---|---|
| **M0** | Skeleton: repo layout, uv workspace, LICENSE/NOTICE, CI, core compose healthy | ✅ done |
| **M1** | ISO 20022 library: bindings, builders/parsers, validator, usage rules, inject, manifest | ✅ done |
| M2 | Banks + switch | ⬜ planned |
| M3 | FDX + FAPI 2.0 | ⬜ planned |
| M4 | Agents + MCP | ⬜ planned |
| M5 | `bankbench` scenarios/oracles | ⬜ planned |
| M6 | Defenses D1–D10 | ⬜ planned |
| M7 | Observability, controls, integrations | ⬜ planned |
| M8 | Stretch (Mojaloop, signed instructions, …) | ⬜ planned |

See [`docs/milestones.md`](docs/milestones.md) and [`SPEC.md`](SPEC.md) §18.

## Project layout

```
deploy/     docker compose + Keycloak realms, PKI, NATS/OPA/OTel config
config/     bank / PSP / switch / model / defense configuration
libs/       Python workspace packages (agentbank_common, _iso, _fdx, _ledger, _gateway)
services/   FastAPI + MCP services (filled M2–M4)
agents/     LLM agent prompts and graphs (M4)
iso20022/   ISO 20022 manifest; XSDs fetched by `make iso-setup` (M1, not committed)
scenarios/  attack scenario catalog S01–S24 (M5)
tasks/      benign user tasks (M4)
templates/  injection templates (M5)
bankbench/  evaluation runner, oracles, metrics, report (M5)
controls/   NIST SP 800-53 mapping and evidence tests (M7)
tests/      unit / integration / e2e / controls
docs/       architecture, getting started, milestones, threat model
```

## License

Apache-2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Copyright 2026 Munawar Ali.
