# Keycloak realms

Four realms are imported at startup (`start-dev --import-realm`):

| Realm | Purpose |
|---|---|
| `bank-a` | Aurora National Bank customers + PSP clients |
| `bank-b` | Birchwood Community Bank customers + PSP clients |
| `bank-c` | Cascade Credit Union members + PSP clients |
| `staff` | Bank staff / ops accounts |

The M0 realm files (`realms/*.json`) are **minimal**: name, `enabled`, `displayName`,
`sslRequired: external`, and empty user/client lists. **No users with passwords and
no client secrets are committed.**

FAPI 2.0 client policies (`fapi-2-security-profile`, `fapi-2-dpop-security-profile`),
DPoP, PAR, `private_key_jwt` clients, PSP registrations, consent scopes and token
exchange are added in **milestone M3** (SPEC §5.2, §12 IA-2/IA-8). Client keypairs
and realm secrets are generated at bootstrap and never committed.
