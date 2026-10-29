# services/psp-core

PSP core service (×3), parameterized: FAPI 2.0 OAuth client, consent/token store, FDX client, its agent, and (psp-pis) merchant/invoice intake.

Defined in SPEC §5.2 (also §3.2). Implemented in **M3** as the FAPI client path in `agentbank_fdx`: PAR, `private_key_jwt`, DPoP (or mTLS at bank-a), and `POST /fdx/v6/payments`. The three PSP ids are `psp-pis`, `psp-pfm`, and `psp-agg` (`config/psps/`).
