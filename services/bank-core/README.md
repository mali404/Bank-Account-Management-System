# services/bank-core

Bank core service (×3), parameterized by `BANK_ID`: double-entry ledger, customers/accounts/payees/payments/consents, the customer app API, the ops API, and the FDX-style API.

Defined in SPEC §5.1 (also §3.1). The ledger, the customer app, and the ops API are implemented in **M2** by `agentbank_ledger` (`World`, `Bank`, `create_bank_app`). The three banks run in that process for tests, `make seed`, and `make reset`. FDX and FAPI 2.0 arrive in **M3**.
