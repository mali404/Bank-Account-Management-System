# Architecture

## 1. Goals

1. **Faithful modernization** of the 2023 course project: keep the five RBAC roles, NIST controls, and dual-layer encryption intent.
2. **Hybrid agency**: LLM agents reason about *what* to do; deterministic services execute *how*. Money never moves through an LLM-generated SQL string.
3. **Auditability over cleverness**: every agent decision and every tool call is traceable, replayable, and tied to a user identity.
4. **Reproducibility**: anyone with Docker can `make up` and reach a working system in under five minutes, without needing API keys.

## 2. Design principles

### 2.1 Separation of reasoning and execution

The hardest lesson from the early agent era (2023–2024) is that letting an LLM directly emit privileged operations is a sustainability dead-end for regulated domains. We split the system into two layers:

- **Reasoning layer** (LangGraph supervisor + role-agents): consumes user intent, plans, asks for clarification, picks tools, summarizes outcomes.
- **Execution layer** (FastAPI + Postgres): exposes a small, well-typed set of banking tools (`open_account`, `transfer`, `freeze_account`, …). Each tool is independently testable and enforces RBAC server-side regardless of which agent called it.

This split means the LLM is effectively *advisory*: it can recommend a transfer, but the FastAPI layer is the system of record and the gatekeeper.

### 2.2 Dual authorization

Authorization is enforced at two layers:

1. **Symbolic policy** in the supervisor — a role-agent only has access to tools its role permits. This is fast and gives clean error messages.
2. **Server-side policy** in FastAPI — every tool endpoint re-verifies the JWT, role, and resource-level permissions (e.g., a customer can only transfer *from* their own accounts). This is the actual security boundary.

If the agent layer is compromised or hallucinates a tool call, the API layer still refuses.

### 2.3 Deterministic tools, observable agents

Tools return structured results with `success`, `data`, and `audit_id` fields. The agent doesn't see encryption keys, raw DB rows, or other users' data — only what the API layer chooses to expose.

Agent execution is instrumented with OpenTelemetry traces. Each LangGraph node becomes a span; tool calls are child spans. This produces a Jaeger waterfall that's a near-perfect agent-replay format.

## 3. Component breakdown

### 3.1 FastAPI edge

- **AuthN**: OAuth2 password flow → JWT (RS256, 15-minute access token, 7-day refresh).
- **AuthZ**: Dependency-injected RBAC checker; supports role hierarchy and resource-level scopes.
- **Rate limiting**: SlowAPI with Redis backend (Redis container in `make up`).
- **Validation**: Pydantic v2 strict models; rejects unknown fields.
- **OTel**: auto-instrumented FastAPI + manual spans for business logic.

### 3.2 LangGraph supervisor

A `StateGraph` with the following nodes:

```
        START
          ▼
    ┌──────────┐
    │ classify │  → determines which role-agent to delegate to
    └────┬─────┘
         ▼
   ┌──────────────┐  conditional edges
   │  supervisor  │ ─── customer_agent
   │              │ ─── teller_agent
   │              │ ─── loan_officer_agent
   │              │ ─── compliance_agent
   │              │ ─── admin_agent
   └──────┬───────┘
          ▼
   ┌──────────────┐
   │  reflect     │  → optional human-in-the-loop interrupt
   └──────┬───────┘
          ▼
        END
```

State is checkpointed via `PostgresSaver`, giving us **durable execution**: if the worker restarts mid-flow, the conversation resumes. This matters for multi-step compliance reviews that might span minutes.

### 3.3 Banking tools (deterministic)

Each tool is a typed function decorated with `@tool` and additionally exposed as a FastAPI route. The agent calls the function; the function in turn calls the API over loopback so audit/RBAC checks fire identically whether invoked by an agent or a direct API client.

Tools, by role:

| Tool | Customer | Teller | Loan Officer | Compliance | Admin |
|---|:-:|:-:|:-:|:-:|:-:|
| `view_my_accounts` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `transfer_funds` (≤ $5k) | ✅ | ✅ | – | – | – |
| `transfer_funds` (> $5k) | – | – | – | ✅ approves | – |
| `open_account` | – | ✅ | – | – | – |
| `originate_loan` | – | – | ✅ | – | – |
| `freeze_account` | – | – | – | ✅ | – |
| `manage_roles` | – | – | – | – | ✅ |

### 3.4 PostgreSQL with pgcrypto + RLS

- **At-rest encryption**: column-level via `pgcrypto`'s `pgp_sym_encrypt` for PII (name, SSN/CNIC, DOB). Bulk volume encryption is the host's responsibility (EBS in AWS).
- **Row-level security**: enabled on `accounts`, `transactions`, `customers`. Policies tie row visibility to the JWT-derived current user / role.
- **Audit log**: append-only `audit_events` with HMAC chaining (each row's HMAC includes the previous row's HMAC) — tamper-evident.

### 3.5 Ollama + Llama 3.1 8B

Model runs in its own container with a healthcheck. Defaults to `llama3.1:8b-instruct-q4_K_M` (≈ 5 GB, fits in 8 GB RAM). Swappable via `LLM_MODEL` env var; e.g., `qwen2.5:7b` for stronger tool-use.

## 4. Threat model (STRIDE-lite)

| Threat | Vector | Mitigation |
|---|---|---|
| **Spoofing** | Stolen JWT | Short access token + refresh rotation; key rotation runbook |
| **Tampering** | Modify audit log to hide fraud | HMAC chain on `audit_events`; periodic anchor to external store |
| **Repudiation** | "I never approved that" | Every approval recorded with user_id, timestamp, IP, action hash |
| **Information disclosure** | SQL injection via agent | All DB access goes through SQLAlchemy parameterized queries; no LLM-generated SQL ever executed |
| **Denial of service** | Agent loop / runaway tool calls | LangGraph step limit (default 12); rate limit at edge; tool-call budget per request |
| **Elevation of privilege** | Prompt injection asking agent to escalate role | Role is server-derived from JWT, never agent-supplied; tools double-check |

### Specific to LLM agents

- **Prompt injection**: agents see only user content classified as *data*, never as instructions. System prompts are pinned per role; user content is wrapped with delimiters and the supervisor is instructed to ignore embedded directives. Plus, since the LLM cannot directly mutate state, the worst-case outcome of a successful injection is a misleading natural-language response — not unauthorized money movement.
- **Tool-output poisoning**: tool results are typed structs; the agent cannot turn a `BalanceResponse` into a transfer.

## 5. Architecture decision records (ADRs)

### ADR-001: LangGraph over CrewAI/AutoGen

**Status**: accepted. **Context**: need durable, observable, multi-actor orchestration with explicit state. **Decision**: LangGraph 1.x. **Consequences**: more boilerplate than CrewAI, but explicit graphs aid auditability — a research-favored property.

### ADR-002: Local Llama 3.1 via Ollama, not hosted API

**Status**: accepted. **Context**: PhD portfolio — reproducibility and cost-zero matter more than peak quality. **Decision**: Ollama default; pluggable via `BaseChatModel`. **Consequences**: slightly weaker tool use vs. GPT-4-class models; mitigated by structured output prompts and JSON schema enforcement.

### ADR-003: Hybrid (LLM advisory + deterministic execution)

**Status**: accepted. **Context**: regulated domain. **Decision**: LLM never executes privileged ops directly; tools are typed APIs. **Consequences**: limits how "agentic" the system feels but produces a clean audit trail.

### ADR-004: PostgreSQL with pgcrypto + RLS over Oracle/MySQL of original

**Status**: accepted. **Context**: open-source, modern, free tier–friendly. **Decision**: Postgres 16. **Consequences**: loses Oracle-specific tested features from original course, gains RLS and pgcrypto.

### ADR-005: OpenTelemetry over LangSmith for observability

**Status**: accepted. **Context**: vendor neutrality, open ecosystem. **Decision**: OTel → Jaeger + Prometheus + Grafana stack. **Consequences**: more setup vs. one-click LangSmith; portable across deployments.

## 6. What was preserved from the 2023 original

- Five RBAC roles and separation-of-duties model.
- NIST SP 800-53 control alignment.
- Dual-layer encryption intent (now: TLS in transit, pgcrypto + age at rest).
- RESTful tool surface (now: FastAPI/OpenAPI, not Flask).
- Multi-database test posture (now: SQLite for unit tests, Postgres for integration).

## 7. What is genuinely new

- LangGraph supervisor with role-specialized agents.
- Durable execution + human-in-the-loop interrupts for high-value flows.
- HMAC-chained tamper-evident audit log.
- OpenTelemetry-based agent traceability — every reasoning step, every tool call.
- CodeQL + Bandit + dependency-review CI pipeline.
- Container-first deploy to AWS ECS with Terraform.
