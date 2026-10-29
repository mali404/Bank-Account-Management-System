# agentbank_fdx

FDX-inspired resource API and the FAPI 2.0 checks the resource server applies. This is not an FDX schema and it is not certified (SPEC §1.1). Field names are authored from public descriptions of accounts, transactions, consents, and a testbed payments extension. Error bodies are `{code, message, debugMessage}`.

Part of the [AgentBank-Sec Testbed](../../README.md). Apache-2.0.

`mount_fdx(app, bank, gate)` adds `/fdx/v6` to a bank app, plus `/oauth/par`, `/oauth/authorize`, and `/oauth/token`.

- Bank-b and bank-c use the DPoP profile. A resource call needs an access token in the `DPoP` scheme and a `DPoP` proof whose `htm`, `htu`, `iat`, and `ath` match the request. The proof's key must match the token's `cnf.jkt`. A missing proof is rejected. A repeated `jti` is rejected.
- Bank-a uses the mTLS profile. The access token's `cnf.x5t#S256` must equal the `X-Client-Cert-Sha256` header presented with the call.
- `/oauth/authorize` accepts only a `request_uri` previously stored by `/oauth/par`. A raw authorization query is rejected.
- The token endpoint accepts `private_key_jwt` (`client_assertion`) and rejects `client_secret`. PKCE S256 is required on the authorization-code grant.
- `POST /fdx/v6/payments` refuses an amount above the consent's `perPaymentMinor` with 403, and a revoked consent with 403. A completed payment is a pacs.008, so the creditor stores a camt.054.

The Keycloak realm files name the built-in profiles `fapi-2-security-profile` (bank-a) and `fapi-2-dpop-security-profile` (bank-b, bank-c) and register the three PSP clients with `client-jwt` and PAR required. Client keys are generated when a world starts and are not committed. The checks above are what the tests run; they do not start Keycloak. An OIDF conformance plan against a live Keycloak is manual.
