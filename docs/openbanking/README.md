# Open Banking (OBIE-Aligned) Surface

This document describes how Agentic Bank exposes an OBIE-aligned API for Account Information Service Providers (AISPs), Payment Initiation Service Providers (PISPs), and the public Open Data tier — and where this implementation deliberately diverges from production OBIE for a portfolio context.

## 1. Scope

Three tiers are implemented:

| Tier | Spec reference | Auth | Endpoints |
|---|---|---|---|
| **Open Data API** | OBIE Open Data v2.x | none | `/open-banking/v4.0/branches`, `/atms`, `/personal-current-accounts` |
| **Read API (AISP)** | OBIE Read/Write v4.0 — Account & Transaction | FAPI + consent | `/account-access-consents`, `/accounts`, `/accounts/{id}/balances`, `/accounts/{id}/transactions` |
| **Write API (PISP)** | OBIE Read/Write v4.0 — Payment Initiation | FAPI + consent | `/domestic-payment-consents`, `/domestic-payments` |

OBIE prescribes ISO 20022-derived JSON schemas. We follow the v4.0 envelope shape (`Data`, `Risk`, `Links`, `Meta`) faithfully on the wire so a real AISP/PISP integration test could swap the base URL.

## 2. The intent / consent model

Vanilla OAuth 2.0 scopes are too coarse for banking ("the TPP can access *any* account") so OBIE layers an **intent-based consent** on top:

```
1. TPP creates a consent resource    POST /account-access-consents
   → ConsentId (server-issued), status=AwaitingAuthorisation
2. TPP redirects PSU (the customer)  to /authorize?openbanking_intent_id={ConsentId}&...
3. PSU authenticates and authorises  the consent → status=Authorised
4. AS issues access token            with the ConsentId bound to it
5. TPP calls Read endpoints          carrying that token; server checks
                                      consent.permissions, consent.expires_at,
                                      and that the requested account is in
                                      consent.account_ids
```

Same pattern for payments, with a `domestic-payment-consent` resource that includes the destination account, amount, and a `Risk` block.

## 3. How this maps onto our existing RBAC

The five existing roles (Customer, Teller, Loan Officer, Compliance Officer, Admin) are unchanged. We add:

- **One actor type**: `ThirdPartyProvider` (TPP). TPPs are registered out-of-band by an Admin and identified by an OAuth `client_id` plus a software statement.
- **One resource type**: `Consent`. A consent is a grant *from* a Customer *to* a TPP, scoped by permissions, time, and (for payments) an amount.
- **One token claim**: `consent_id`. The token issued to a TPP after consent authorisation carries this claim. Every TPP request checks it.

The agent layer is untouched: TPPs are machine actors and hit the typed APIs directly, not the agent supervisor. Customers can still chat with the supervisor; AISPs and PISPs talk to OBIE endpoints.

## 4. FAPI compliance — what we do and don't implement

FAPI 1 Advanced is the security profile OBIE mandates today (the older "Open Banking Security Profile" is deprecated). For a portfolio piece we implement the structurally meaningful parts and explicitly document the parts we don't:

| FAPI requirement | This repo |
|---|---|
| TLS 1.2+ everywhere | ✅ via Caddy in dev, ALB in prod |
| OIDC `id_token` carries the consent intent | ✅ in the consent-bound token issuance |
| `aud` claim tied to TPP `client_id` | ✅ |
| **mTLS with TPP eIDAS QWAC certificates** | ❌ — we use a stub: TPPs register a self-signed cert in dev. Documented gap. |
| **JWS-signed request objects (JAR / RAR)** | ⚠️ Partial — we accept signed request objects but don't enforce them on every endpoint. |
| **Detached JWS signatures on responses** | ⚠️ Partial — implemented for payment-initiation responses; not for read endpoints. |
| **PAR (Pushed Authorization Requests)** | ❌ — out of scope; documented gap. |
| **Software Statement Assertion (SSA) verification** | ❌ — TPP registration is admin-driven instead of OBIE Directory-driven. |

Why the gaps are honest, not lazy: a real ASPSP integrates with the OBIE Directory and processes eIDAS certificates issued by qualified providers — that infrastructure isn't reproducible in a portfolio repo. We mark each gap with a `# OBIE-GAP:` comment so a reviewer can find them at a glance.

## 5. Endpoints implemented

### Open Data (no auth)

```
GET /open-banking/v4.0/branches
GET /open-banking/v4.0/atms
GET /open-banking/v4.0/personal-current-accounts
```

These return `Data`-wrapped responses with a small synthetic catalogue suitable for demos.

### AISP (Account Information)

```
POST /open-banking/v4.0/aisp/account-access-consents      # create consent
GET  /open-banking/v4.0/aisp/account-access-consents/{id} # read consent status
DELETE /open-banking/v4.0/aisp/account-access-consents/{id}
GET  /open-banking/v4.0/aisp/accounts
GET  /open-banking/v4.0/aisp/accounts/{id}
GET  /open-banking/v4.0/aisp/accounts/{id}/balances
GET  /open-banking/v4.0/aisp/accounts/{id}/transactions
```

### PISP (Payment Initiation)

```
POST /open-banking/v4.0/pisp/domestic-payment-consents
GET  /open-banking/v4.0/pisp/domestic-payment-consents/{id}
POST /open-banking/v4.0/pisp/domestic-payments            # creates an internal Transaction
GET  /open-banking/v4.0/pisp/domestic-payments/{id}
```

A PISP-initiated payment runs through the **same** internal `Transaction` machinery as a customer-initiated one. That means: high-value threshold, separation-of-duties, audit chain — all fire identically. The OBIE layer is a thin protocol adapter; the bank's policy is one source of truth.

## 6. ID-token consent binding

Standard OAuth issues an access token bound to scopes; OBIE additionally requires the `id_token` to carry an `openbanking_intent_id` claim that lets an ASPSP map the token back to the specific consent. Our implementation:

- The consent-authorisation endpoint mints a token with `consent_id` in both the access token (custom claim) and the `id_token`.
- Every Read/Write endpoint extracts `consent_id`, loads the consent, and verifies:
  1. The consent is `Authorised` (not revoked, not expired).
  2. The requested account is among `consent.account_ids` (for AISP) or matches `consent.debtor_account_id` (for PISP).
  3. The requested permission is in `consent.permissions` (e.g., `ReadAccountsBasic`).

If any check fails: `403` with an OBIE error envelope (`Code: UK.OBIE.Resource.NotAuthorised`, etc.).

## 7. The audit story

Every consent lifecycle event (`create`, `authorise`, `revoke`, `expire`) emits an `audit_events` row tagged with the NIST control (`AC-2`, `AC-3`) and the TPP `client_id`. PISP-initiated payments inherit the existing transfer audit. The HMAC chain extends naturally — Open Banking just adds new event types, not new event schemas.

## 8. What this gets you, narrative-wise

For a PhD application, the addition matters because it shows you understand:

1. **Real banking interop standards**, not just textbook RBAC.
2. **Consent as a first-class object** — a research-rich area at the intersection of capability-based security, distributed authorisation, and HCI.
3. **Honest scoping** — explicit gaps with rationale beat hand-waved completeness every time.

This dovetails with `docs/research_notes.md`: "compositional auditability" and "trust-calibrated delegation" both extend naturally to the TPP-consent setting (e.g., *what's the right granularity of consent for an agentic third party that itself uses sub-agents?*).
