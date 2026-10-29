# Keycloak realms

Four realms are imported at startup (`start-dev --import-realm`):

| Realm | Purpose |
|---|---|
| `bank-a` | Aurora National Bank customers + PSP clients |
| `bank-b` | Birchwood Community Bank customers + PSP clients |
| `bank-c` | Cascade Credit Union members + PSP clients |
| `staff` | Bank staff / ops accounts |

Bank realms declare the FAPI 2.0 client policy Keycloak ships:
`fapi-2-security-profile` on bank-a (mTLS-bound tokens) and
`fapi-2-dpop-security-profile` on bank-b and bank-c. Each bank realm registers
`psp-pis`, `psp-pfm`, and `psp-agg` as confidential `client-jwt` clients with
PKCE S256 and pushed authorization requests required. **No users with passwords
and no client secrets are committed.** Client keypairs are generated when a
simulated world starts.

The resource-server checks the tests run live in `agentbank_fdx.fapi`. They
match those policies without starting Keycloak. An OIDF conformance run against
a live Keycloak is manual. Token exchange for down-scoped agent tokens is
still a later step (SPEC §7).
