# services/sim-mail

A tiny in-repo mailbox service (FastAPI + Postgres `sim_mail` schema); no SMTP relay.

Defined in SPEC §3.4. Implemented in **M4** as `agentbank_gateway.sims.Mailbox` (inbox and outbox). The compose service is the same mailbox once the app containers run.
