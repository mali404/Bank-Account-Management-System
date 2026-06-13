# Pre-Release Code Review

A full design/code/test audit performed before first local run. Every finding below is fixed in this revision and pinned by `tests/security/test_code_review_regressions.py`.

## Findings and resolutions

| # | Severity | Location | Defect | Fix |
|---|---|---|---|---|
| 1 | Critical | OBIE routers | `SessionDep` chains to user-JWT auth; TPP callers (Basic auth / TPP tokens without a `role` claim) would 401 on **every** AISP/PISP/token endpoint. | New `PlainSessionDep` (no user auth, no RLS vars) for TPP-facing endpoints; PSU-facing `authorise-consent` keeps the user session. |
| 2 | Critical | OBIE reads × RLS | TPP sessions set no `app.user_id`/`app.role`; with `FORCE ROW LEVEL SECURITY`, policies default-deny → AISP reads return zero rows. | `set_psu_rls_context()`: after consent validation, the session adopts the consenting PSU's identity — row visibility is bounded by the PSU's ownership, *and* consent scoping applies on top. Two independent layers. |
| 3 | Critical | `Dockerfile` | `pip install .` ran before `app/` (and `README.md`, referenced by pyproject) were copied → build fails; and `--prefix=/install` site-packages was never added to `PYTHONPATH` → runtime `ModuleNotFoundError`. | Copy `pyproject.toml README.md app/` before install; `PYTHONPATH=/app:/install/lib/python3.12/site-packages`; runtime image installs only prod deps. |
| 4 | Critical | compose + `.env.example` | Secrets mount at `/run/secrets/jwt_private` but env pointed at `…/jwt_private.pem` → `FileNotFoundError` at first login. | App service overrides the four secret-path env vars to match the actual mounts. |
| 5 | High | `auth_router`, `transfers_router`, PISP | Audit events for **denied** outcomes were written, then `HTTPException` raised in the same transaction → rollback destroyed the record. Failed logins and blocked self-approvals — exactly the events NIST AU-2 requires — were never persisted. | `write_event_standalone()` commits in its own transaction; all denied-then-raise paths use it. |
| 6 | High | seed scripts | Seeds connected as `agentic_app`; `FORCE RLS` `WITH CHECK` blocks inserting rows for identities not in session context → seeding fails. | Seeds use the admin (superuser) connection, which bypasses RLS by design. |
| 7 | High | `transfers_router.approve` | The insufficient-funds-at-approval path set `state="rejected"` + audit, then raised → both rolled back; the transfer stayed `pending_approval` forever. | Rejection state-change + audit run in a dedicated committed transaction before the 409 is raised. |
| 8 | Medium | `audit.py` | (a) Concurrent writers could read the same `prev_hmac` → forked chain, false tamper alarms. (b) Verification re-serialized from JSONB, which normalizes key order/numerics → legitimate rows could fail verification. | (a) `pg_advisory_xact_lock` serializes appends (Postgres only; guarded by dialect check). (b) New `payload_canonical TEXT` column stores the exact HMAC'd bytes; `verify_chain` reads only that. |
| 9 | Medium | `main.py` | SlowAPI `Limiter` was constructed but never wired (no middleware, no 429 handler) → rate limiting silently inert. | `SlowAPIMiddleware` + `RateLimitExceeded` handler registered; Redis storage configured; `redis` added to deps. |
| 10 | Low | CI | `pip-audit -r <(pip compile …)` — `pip compile` is not a command; the job always errored. | Install the project, then run `pip-audit` against the environment. |
| 11 | Low | `tpp_auth.py` | Unused imports (`OAuth2PasswordBearer`, `get_session_with_rls`, `AsyncSession`). | Removed. |
| 12 | Critical (design) | transfers + PISP settlement | Under the caller's RLS context the **payee's** account row is invisible (correctly!) — so customer→customer transfers and the PISP credit leg would 404. The payer must never read the payee's ledger, yet settlement must credit it. | Two-phase pattern, mirroring real core banking: ownership of the *source* is proven under the caller's RLS context (a successful read **is** the ownership proof), then settlement runs under a dedicated `system` RLS context recognized by the policies. App-level RBAC checks all still precede the escalation. |

## Notes on what the review deliberately did not change

- **The pre-LLM trust boundary** (agents → loopback HTTP → API policy) was re-verified and stands: even with finding #1, agent-driven flows were unaffected because agents carry real user JWTs.
- **Unit/security test suite semantics** are unchanged; 8 regression tests were added (50 total).
- **Known OBIE gaps** (mTLS/eIDAS, PAR, JAR/RAR, Directory integration) remain documented gaps, not defects — see `docs/openbanking/README.md`.

## Honest residual risks (pre-first-run)

These cannot be fully verified without running the stack, and are the first things to watch on `make up`:

1. **Ollama tool-calling quality** with `llama3.1:8b-q4` is serviceable but not flawless; if role-agents mis-format tool calls, switch `LLM_MODEL` to `qwen2.5:7b`.
2. **LangChain/LangGraph 1.x API drift** — `create_agent` signatures have moved between minor versions; if imports fail, pin exact versions from `pip freeze` after first successful run.
3. **First-boot ordering** — Postgres init scripts (001→003) run only on a fresh volume; if you ever change migrations, `docker compose down -v` first.
4. **Integration tests** (`tests/integration/`) exercise the live stack and were not runnable in this environment; run `make up && make seed && make test-integration` to close the loop.
