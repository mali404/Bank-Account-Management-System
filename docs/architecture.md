# Architecture

This is a short orientation. The authoritative design is [`../SPEC.md`](../SPEC.md).

## Topology

- **3 banks** (`bank-core` ×3): Aurora National (`bank-a`), Birchwood Community
  (`bank-b`), Cascade Credit Union (`bank-c`). Each exposes an app API, an ops
  API, and an FDX-inspired API, backed by a double-entry PostgreSQL ledger
  (schema per bank). See SPEC §3.1, §5.1.
- **3 PSPs** (`psp-core` ×3): LedgerLink aggregator (`psp-agg`), PayPath payment
  initiator (`psp-pis`), Penny agentic PFM (`psp-pfm`). See SPEC §3.2, §5.2.
- **1 switch** (`switch`, "SimNow"): FedNow-inspired instant-payment switch over
  ISO 20022 with TigerBeetle settlement and a hash-chained archive. See SPEC
  §1.2, §5.3.
- **Agents** (LangGraph primary) call **MCP tool servers** through the
  **agent-gateway**, which applies pluggable defenses. See SPEC §5.4–§5.5, §7, §9.

## Supporting infrastructure (M0)

- **Keycloak** — identity provider / FAPI 2.0 authorization server (SPEC §5.2).
- **step-ca** — internal PKI for mTLS (SPEC §12 IA-3/SC-8).
- **PostgreSQL + pgvector** — bank ledgers and the bank-c RAG KB (SPEC §5.1).
- **NATS JetStream** — switch ↔ bank ISO 20022 transport (SPEC §5.3).

## Networks (SPEC §15)

`edge` (host-exposed), `bank-net`, `switch-net`, `agent-net` (all `internal`),
and `egress` (opt-in LLM-API access only). This segmentation implements SC-7
boundary protection. In M0 only Keycloak is host-exposed.

## Stable interfaces

The results-row schema, the `Defense` plugin protocol, and the oracle signature
are stable interfaces (SPEC §19), implemented in `agentbank_common` and
`agentbank_gateway`.
