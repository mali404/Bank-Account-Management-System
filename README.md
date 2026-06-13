# Agentic Bank — A Hybrid Multi-Agent Banking System with NIST-Aligned Security

> A modern reimagining of *Multi-Agent Banking System with Robust Security and Encryption* (ITMD‑523 / ITMS‑528, Illinois Institute of Technology, 2023), rebuilt around stateful LLM-orchestrated agents, deterministic banking services, and production-grade observability. Conceived as a portfolio piece supporting research interests in **role-based multi-agent autonomous systems for complex financial operations**.

## Why this project exists

The original course project demonstrated five RBAC roles, NIST SP 800-53 controls, and dual-layer encryption against a Flask + RESTful backbone. That blueprint is sound, but the agent paradigm has shifted: production-grade agents are now **stateful graphs with durable execution, human-in-the-loop gates, and explicit observability**, not request-response handlers.

This rebuild keeps the original's strongest ideas — RBAC, separation of duties, dual-layer encryption, audit-grade logging — and routes them through a **hybrid architecture**: an LLM orchestration layer (LangGraph) coordinates **deterministic** banking services (FastAPI + PostgreSQL) so that *reasoning* happens in the agent layer while *money movement* happens under verifiable, testable contracts.

## Architecture at a glance

```
                ┌─────────────────────────────────────────────┐
                │              Client (CLI / curl)            │
                └────────────────────┬────────────────────────┘
                                     │  JWT (RS256)
                                     ▼
            ┌─────────────────────────────────────────────────┐
            │          FastAPI Edge — AuthN, RBAC, OTel       │
            └───┬───────────────────┬───────────────────────┬─┘
                │                   │                       │
                ▼                   ▼                       ▼
       ┌─────────────────┐  ┌────────────────┐    ┌─────────────────┐
       │  LangGraph      │  │  Deterministic │    │  Audit Service  │
       │  Supervisor     │──▶  Banking Tools │    │  (append-only)  │
       │  (5 role-agents)│  │  (transfer,    │    │                 │
       └────────┬────────┘  │   freeze,KYC)  │    └────────┬────────┘
                │           └────────┬───────┘             │
                │                    │                     │
                │                    ▼                     │
                │           ┌────────────────┐             │
                │           │   PostgreSQL   │◀────────────┘
                │           │  (pgcrypto +   │
                │           │   row-level    │
                │           │   security)    │
                │           └────────────────┘
                ▼
       ┌─────────────────┐
       │  Ollama (local) │
       │  Llama 3.1 8B   │
       └─────────────────┘
```

Reasoning trajectories, tool calls, and policy decisions stream into **OpenTelemetry → Jaeger + Prometheus + Grafana** so every agent action is traceable post-hoc — a must-have for any banking-adjacent system.

## The five RBAC roles (preserved from the original)

| Role | Capabilities | Cannot do |
|---|---|---|
| **Customer** | View own accounts, initiate transfers under daily limit | Approve high-value transfers, modify other users |
| **Teller** | Open accounts, low-value transfers, KYC submissions | Approve high-value, manage roles |
| **Loan Officer** | Read credit profile, originate loans | Move customer funds outside loan flow |
| **Compliance Officer** | Freeze/unfreeze accounts, audit reads, AML flags | Originate transactions |
| **Admin** | Role management, key rotation, system config | Approve own transactions (separation of duties) |

The agent supervisor decomposes a natural-language request, asks the right role-agent, and the role-agent calls only the deterministic tools its role permits. Authorization is enforced *twice*: once symbolically by the agent, once again by the FastAPI policy layer. Belt and suspenders.

## NIST SP 800-53 controls implemented

| Family | Control | How it shows up |
|---|---|---|
| AC | AC-2, AC-3, AC-5, AC-6 | RBAC tables, separation of duties checks, least-privilege tool exposure |
| AU | AU-2, AU-3, AU-9, AU-12 | Append-only audit log with HMAC chaining, structured event records |
| IA | IA-2, IA-5 | JWT (RS256) with rotating keys, password hashing via Argon2id |
| SC | SC-8, SC-13, SC-28 | TLS in transit (mkcert in dev), pgcrypto + age for data at rest |
| SI | SI-3, SI-4, SI-7 | Bandit + CodeQL on CI, OTel traces for anomaly detection |

## Quickstart

```bash
git clone <your-fork> agentic-bank
cd agentic-bank
cp .env.example .env
make up          # docker compose: postgres, ollama, jaeger, prometheus, grafana, app
make seed        # creates the five roles, demo users, demo accounts
make demo        # runs an end-to-end scripted scenario you can watch in Jaeger
```

Then open:
- **API docs** → http://localhost:8000/docs
- **Jaeger** (agent traces) → http://localhost:16686
- **Grafana** (metrics) → http://localhost:3000

## Open Banking (OBIE-aligned)

A complete UK Open Banking surface sits alongside the internal API, modelled on OBIE Read/Write v4.0:

- **Open Data API** (no auth): `/open-banking/v4.0/branches`, `/atms`, `/personal-current-accounts`
- **AISP** (account information, FAPI + consent): `/account-access-consents`, `/accounts`, `/accounts/{id}/balances`, `/accounts/{id}/transactions`
- **PISP** (payment initiation, FAPI + consent): `/domestic-payment-consents`, `/domestic-payments`
- **OAuth/token**: `/open-banking/oauth/token` (client_credentials + intent grant), `/open-banking/oauth/authorise-consent`

Consent is enforced as a first-class object: every TPP token carries a `consent_id` and every request is checked against the consent's `permissions`, `account_ids`, `expiration_at`, and `tpp_id`. PISP-initiated payments flow through the same internal `Transaction` machinery as customer-initiated ones, so high-value approval, separation of duties, and the audit chain apply identically.

Honest scoping: this is OBIE-shaped, not OBIE-certified — mTLS with eIDAS certs, PAR, JAR/RAR, JWS-signed responses on every endpoint, and OBIE Directory integration are documented gaps marked `# OBIE-GAP:` in the code. See [`docs/openbanking/README.md`](docs/openbanking/README.md) for the full mapping.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — full design rationale, threat model, ADRs
- [`docs/security.md`](docs/security.md) — NIST control mapping, key management
- [`docs/agents.md`](docs/agents.md) — LangGraph supervisor + role-agent design
- [`docs/testing.md`](docs/testing.md) — testing strategy across unit, integration, security
- [`docs/deployment.md`](docs/deployment.md) — local → AWS ECS deployment guide
- [`docs/openbanking/README.md`](docs/openbanking/README.md) — **UK Open Banking (OBIE) v4.0 surface** — Open Data, AISP, PISP
- [`docs/research_notes.md`](docs/research_notes.md) — open research questions for PhD framing

## License

MIT. See [`LICENSE`](LICENSE).
