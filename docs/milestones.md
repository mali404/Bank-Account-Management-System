# Milestones

Tracks the milestone plan in [`../SPEC.md`](../SPEC.md) §18.

| M | Deliverable | Status |
|---|---|---|
| **M0** | Skeleton: repo layout, uv workspace, Apache-2.0 LICENSE/NOTICE, CI (ruff, mypy, pytest), compose with Postgres/NATS/Keycloak/step-ca healthy | ✅ done |
| **M1** | ISO 20022 library: xsdata bindings, builders/parsers, validator, usage rules, inject helpers, MANIFEST | ✅ done |
| **M2** | Banks + switch: bank-core ×3, switch pipeline, TigerBeetle settlement, returns, RfP, archive | ✅ done |
| **M3** | FDX + FAPI 2.0: FDX-style API, consents, payments, 3 PSPs, Keycloak FAPI policies, DPoP/PAR/private_key_jwt, mTLS | ✅ done |
| **M4** | Agents + MCP: 6 agents on LangGraph, MCP servers, gateway (D0), sim-mail, merchant-sim, user-sim, ≥30 benign tasks | ✅ done |
| **M5** | bankbench: scenarios S01–S24, templates, oracles, runner, metrics, parquet + report | ✅ done |
| **M6** | Defenses: D1–D10 plugins, OPA policies, CaMeL-style mode, HITL models | ⬜ planned |
| **M7** | Obs, controls, integrations: OTel/Jaeger/OpenSearch, controls.yaml + check_baselines.py, OpenAI Agents SDK, adapters | ⬜ planned |
| **M8** | Stretch: Mojaloop overlay, AU-10 signed instructions, Canada CDB profile, A2A protocol, web-agent channel | ⬜ planned |

**Definition of done (v1.0 = M0–M7):** a fresh clone runs
`make bootstrap up seed bench MODEL=<local> DEFENSE=D0,D4` and produces
`results/<run>/report.md` with ASR/BU/UA/UTV tables and CIs, with all tests green.

## M0 acceptance

- `make bootstrap up` is green on a clean machine.
- `make test` passes.

## M1 acceptance

- `make iso-setup` downloads every SPEC §6.1 XSD from iso20022.org and checks
  it against `iso20022/xsd/MANIFEST.yaml`; `make xsd-verify` then passes offline.
- `make test` (Hypothesis profile `ci`, 1,000 examples per message) round-trips
  every message, rejects the invalid fixtures with a field path, and enforces
  the XSD `maxLength` limits (140 for `Nm` / `Ustrd`, 105 for `AddtlInf`, 500
  for `AddtlNtryInf`, 350 for `RsnDesc`).
- API, the field-limit table and the charset profiles are documented in
  [`libs/agentbank_iso/README.md`](../libs/agentbank_iso/README.md). The schemas
  themselves are fetched, not committed; see [`iso20022/README.md`](../iso20022/README.md).

## M2 acceptance

- A pacs.008 from bank-b to bank-a settles `ACSC` in under 2 seconds. Customer balances move by the amount, the settlement positions sum to zero, each bank's settlement GL matches its switch position, suspense is clear, and the archive hash chain verifies (`tests/unit/test_m2_acceptance.py`).
- Replaying the same envelope is `RJCT` / `AM05` and does not credit the creditor again.
- An amount above the switch participant limit is `RJCT` / `AM02` with no pending debit left open.
- A creditor response delay above the 20 second receiver timeout is `RJCT` / `AB05` and voids the pending transfer. The comparison stands in for a NATS request deadline, so the suite does not sleep.
- camt.056 followed by pacs.004 returns the funds and restores both settlement positions.
- Tampering with one archived blob fails `hash_chain_ok`.
- pain.013 is forwarded, pain.014 is answered, and paying the RfP ends in `ACSC`.
- `World.reset` and `make reset` (`scripts/reset_state.py`) restore the seed snapshot in under 30 seconds. `seed_world(..., 42)` is deterministic.
- The three banks and the switch run in one process (`agentbank_ledger.world.World`). Settlement follows TigerBeetle's pending / post / void counters and does not connect to a TigerBeetle cluster. See [`libs/agentbank_ledger/README.md`](../libs/agentbank_ledger/README.md).

## M3 acceptance

- A DPoP-scheme token presented to bank-b without a `DPoP` proof, or as `Bearer`, is 401. The same call with a proof whose `htm`, `htu`, and `ath` match is 200 (`tests/unit/test_m3_acceptance.py`).
- Replaying that proof (`jti`) is 401.
- `GET /oauth/authorize` without a PAR `request_uri` is 400. `client_secret` on the token endpoint is 401; `private_key_jwt` is what issues the token.
- A payment above the consent `perPaymentMinor` is 403 `CONSENT_LIMIT`. After revocation the same consent is 403 `CONSENT_REVOKED`. No camt.054 is stored.
- A PSP payment inside the consent settles `COMPLETED` and the creditor bank holds a camt.054 (`BkToCstmrDbtCdtNtfctn`).
- Bank-a rejects a token whose `X-Client-Cert-Sha256` does not match `cnf.x5t#S256`.
- Realm JSON names `fapi-2-security-profile` (bank-a) and `fapi-2-dpop-security-profile` (bank-b, bank-c) and registers the three PSP clients with no secrets.
- The prowide sidecar is not wired: Maven Central has `pw-iso20022` `SRU2024-10.2.7`, and the SRU2025-10.4 line in SPEC §6.2 is not published there. See [`services/iso-validator/README.md`](../services/iso-validator/README.md). OIDF conformance against a live Keycloak is manual.

## M4 acceptance

- Six LangGraph agents (cba, ops, rec, ppa, pen, ins) each complete their benign tasks under D0 with the reference model. Documented benign utility is 1.0, and the suite meets it (`tests/unit/test_m4_acceptance.py`, `tasks/T001.yaml`–`T030.yaml`).
- Every tool call is traced with the run id before the tool body runs.
- Tool registries for `mcp-bank`, `mcp-ops`, `mcp-psp`, `mcp-mail-docs`, and `mcp-kb` carry a risk class and return `TaggedValue`. Description hashes are pinned in each service `inventory.yaml`.
- sim-mail, merchant-sim, and user-sim (`always-approve`, `careful`, `fatigue`) run in process.

## M5 acceptance

- `scenarios/S01.yaml`–`S24.yaml` load, and each names a template under `templates/injections/` and an oracle in `bankbench.oracles` (`tests/unit/test_m5_acceptance.py`).
- `run_catalog` runs every scenario twice (benign twin and injection). Under D0 the mock sets the attack flag and the success oracle is true. The benign twin keeps `utility_success` and a false attack oracle.
- A second profile name (`D4`) is recorded with the attack oracle false. That is the mock, not an implementation of D4 (D1–D10 are M6).
- Two runs with seed 42 produce the same rows, including the anchor timestamp `2026-10-29T15:00:00Z`.
- Every oracle has a forced-success snapshot and a forced-failure snapshot.
- `write_run` writes `results.parquet` in `RESULTS_COLUMN_NAMES` order and a `report.md` with ASR, BU, UA, UTV, and Wilson 95% intervals.
- `make bench` and `make report` call `python -m bankbench`. See [`bankbench/README.md`](../bankbench/README.md).
