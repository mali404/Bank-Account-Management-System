# services

FastAPI and MCP tool services (SPEC §5, §14). All are placeholders in M0.

| Service(s) | Purpose | Milestone |
|---|---|---|
| `bank-core/` | Bank cores ×3 (ledger, app/ops/FDX APIs, consents) | **M2** / **M3** |
| `switch/` | SimNow instant-payment switch (ISO 20022, settlement, archive) | **M2** |
| `psp-core/` | PSP cores ×3 (FAPI 2.0 clients, consents, agents) | **M3** |
| `sim-mail/` | In-repo mailbox service | **M4** |
| `merchant-sim/`, `user-sim/`, `attacker-console/` | Simulated parties | **M4** |
| `mcp-bank/`, `mcp-psp/`, `mcp-mail-docs/`, `mcp-kb/`, `mcp-ops/`, `mcp-evil/` | MCP tool servers | **M4** |
| `iso-validator/` | Java 21 prowide cross-validator sidecar | **M3** |
