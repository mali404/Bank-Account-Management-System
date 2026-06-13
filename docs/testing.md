# Testing Strategy

Testing for a regulated, agent-driven system needs three distinct layers because each rules out a different class of failure.

## 1. Unit tests (`tests/unit/`)

Small, fast, no external services. Run on every save.

| File | What it pins down |
|---|---|
| `test_rbac.py` | Policy matrix is the source of truth; new permissions don't accidentally leak to wrong roles. |
| `test_auth.py` | Argon2id round-trip; JWT signature/algorithm rejection (defends against the classic "use the public key as an HS256 secret" forgery). |
| `test_audit_chain.py` | HMAC chain is deterministic and breaks under any mutation. |

Goal: < 5 seconds, no Docker.

## 2. Security tests (`tests/security/`)

Encode banking invariants as named tests. A security reviewer should be able to read the file names and know what's enforced.

| Test | NIST control | Statement |
|---|---|---|
| `test_separation_of_duties_pillar_admin_no_money` | AC-5 / AC-6 | Admin role has no money-movement permissions. |
| `test_only_one_role_can_freeze_accounts` | AC-3 | Only compliance can freeze. |
| `test_only_one_role_can_originate_loans` | AC-3 | Only loan officers originate. |
| `test_only_one_role_can_manage_roles` | AC-2 | Only admins manage roles. |
| `test_tools_by_role_align_with_policy_matrix` | AC-3 | Agent tool exposure cannot exceed policy matrix. |
| `test_admin_has_no_money_tools` | AC-5 | Belt-and-suspenders: structurally impossible for admin agent to even *attempt* a transfer. |

These are a separately-runnable suite (`make test-security`). When you change any RBAC, you re-run security tests first.

## 3. Integration tests (`tests/integration/`)

Real Postgres, real FastAPI, real RLS policies. Drive the public HTTP API. Run after `make up && make seed`.

| Test | Asserts |
|---|---|
| `test_health` | Smoke. |
| `test_customer_login_and_view_own_accounts` | Login flow + RLS scoping. |
| `test_customer_cannot_freeze` | API-layer 403 for missing permission. |
| `test_admin_cannot_transfer` | AC-5 enforced at the HTTP boundary. |
| `test_high_value_transfer_requires_approval` | Threshold gating. |
| `test_originator_cannot_self_approve` | AC-5 even when role would otherwise allow. |

## 4. What's deliberately left out (and why)

- **Load tests**: a portfolio piece doesn't need k6 numbers; the architecture is the artifact. Mention in `research_notes.md` as future work.
- **Live LLM agent tests**: an integration test that hits a real LLM is non-deterministic and slow. The supervisor's *structural* properties are tested (tool-set per role); the LLM's *behavioral* properties belong in eval harnesses (LangSmith, Ragas) and would be the natural extension for a research follow-up.
- **Mutation testing**: would be valuable, especially on the RBAC matrix and audit chain. Listed as a stretch goal.

## 5. Coverage targets

- **Unit + security**: 90 %+ on `app/security/`, `app/observability/audit.py`, `app/api/transfers_router.py`.
- **Integration**: every public endpoint touched at least once with both an authorized and unauthorized actor.

## 6. CI gate

The CI workflow blocks merges on:
- ruff lint + format
- mypy strict
- unit + security tests passing
- bandit (warn-only initially; error-only later)
- pip-audit (warn-only initially)
- CodeQL (uploaded; alerts visible in the Security tab)
- Trivy on the built image (HIGH/CRITICAL surfaced via SARIF)

This matches the original course project's CodeQL emphasis but extends to the supply chain.
