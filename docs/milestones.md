# Milestones

Tracks the milestone plan in [`../SPEC.md`](../SPEC.md) §18.

| M | Deliverable | Status |
|---|---|---|
| **M0** | Skeleton: repo layout, uv workspace, Apache-2.0 LICENSE/NOTICE, CI (ruff, mypy, pytest), compose with Postgres/NATS/Keycloak/step-ca healthy | ✅ done |
| **M1** | ISO 20022 library: xsdata bindings, builders/parsers, validator, usage rules, inject helpers, MANIFEST | ⬜ planned |
| **M2** | Banks + switch: bank-core ×3, switch pipeline, TigerBeetle settlement, returns, RfP, archive | ⬜ planned |
| **M3** | FDX + FAPI 2.0: FDX-style API, consents, payments, 3 PSPs, Keycloak FAPI policies, DPoP/PAR/private_key_jwt, mTLS, prowide cross-validator | ⬜ planned |
| **M4** | Agents + MCP: 6 agents on LangGraph, MCP servers, gateway (D0), sim-mail, merchant-sim, user-sim, ≥30 benign tasks | ⬜ planned |
| **M5** | bankbench: scenarios S01–S24, templates, oracles, runner, metrics, parquet + report | ⬜ planned |
| **M6** | Defenses: D1–D10 plugins, OPA policies, CaMeL-style mode, HITL models | ⬜ planned |
| **M7** | Obs, controls, integrations: OTel/Jaeger/OpenSearch, controls.yaml + check_baselines.py, OpenAI Agents SDK, adapters | ⬜ planned |
| **M8** | Stretch: Mojaloop overlay, AU-10 signed instructions, Canada CDB profile, A2A protocol, web-agent channel | ⬜ planned |

**Definition of done (v1.0 = M0–M7):** a fresh clone runs
`make bootstrap up seed bench MODEL=<local> DEFENSE=D0,D4` and produces
`results/<run>/report.md` with ASR/BU/UA/UTV tables and CIs, with all tests green.

## M0 acceptance

- `make bootstrap up` is green on a clean machine.
- `make test` passes.
