"""End-to-end Open Banking demo.

Walks through:
  1. AISP flow: TPP creates consent → PSU authorises → TPP gets bound
     token → TPP reads accounts and balances.
  2. PISP flow: TPP creates payment consent → PSU authorises with debtor
     account → TPP gets bound token → TPP submits payment → settles as
     an internal Transaction.
  3. Negative paths: out-of-scope account, wrong TPP, revoked consent.

Run via:  python -m scripts.demo_obie
"""
from __future__ import annotations

import asyncio
import base64
import os

import httpx
from rich.console import Console

API = os.environ.get("INTEGRATION_API", "http://localhost:8000")
console = Console()


def basic(client_id: str, secret: str) -> dict[str, str]:
    raw = f"{client_id}:{secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


async def main() -> None:
    async with httpx.AsyncClient(base_url=API, timeout=10) as c:
        console.rule("[bold cyan]1. AISP — Acme Aggregator reads account data")

        # 1a. TPP gets a client-credentials token to create a consent.
        r = await c.post(
            "/open-banking/oauth/token",
            data={"grant_type": "client_credentials", "scope": "accounts"},
            headers=basic("acme-aisp", "acme-secret-001"),
        )
        cc_tok = r.json()["access_token"]
        console.print(f"  client_credentials token issued (expires_in={r.json()['expires_in']}s)")

        # 1b. TPP creates a consent specifying which permissions it wants.
        r = await c.post(
            "/open-banking/v4.0/aisp/account-access-consents",
            json={
                "Data": {
                    "Permissions": [
                        "ReadAccountsBasic",
                        "ReadAccountsDetail",
                        "ReadBalances",
                        "ReadTransactionsDetail",
                    ]
                },
                "Risk": {},
            },
            headers={"Authorization": f"Bearer {cc_tok}"},
        )
        consent_id = r.json()["Data"]["ConsentId"]
        console.print(f"  AISP consent created: {consent_id} (Awaiting PSU authorisation)")

        # 1c. PSU logs in and authorises the consent (binding their accounts).
        psu = (await c.post("/auth/token", data={"username": "alice@example.com", "password": "ChangeMe-DemoPw#2025"})).json()
        psu_tok = psu["access_token"]
        accounts = (await c.get("/accounts/me", headers={"Authorization": f"Bearer {psu_tok}"})).json()
        r = await c.post(
            "/open-banking/oauth/authorise-consent",
            json={
                "consent_id": consent_id,
                "consent_type": "aisp",
                "account_ids": [accounts[0]["id"]],
            },
            headers={"Authorization": f"Bearer {psu_tok}"},
        )
        console.print(f"  PSU authorised consent: status={r.json()['status']}")

        # 1d. TPP exchanges consent for a bound token.
        r = await c.post(
            "/open-banking/oauth/token",
            data={"grant_type": "intent", "consent_id": consent_id, "scope": "accounts"},
            headers=basic("acme-aisp", "acme-secret-001"),
        )
        aisp_tok = r.json()["access_token"]
        console.print("  consent-bound token issued")

        # 1e. TPP reads.
        r = await c.get(
            "/open-banking/v4.0/aisp/accounts",
            headers={"Authorization": f"Bearer {aisp_tok}"},
        )
        console.print(f"  GET /accounts → {r.status_code}, {len(r.json()['Data']['Account'])} account(s) returned")

        r = await c.get(
            f"/open-banking/v4.0/aisp/accounts/{accounts[0]['id']}/balances",
            headers={"Authorization": f"Bearer {aisp_tok}"},
        )
        bal = r.json()["Data"]["Balance"][0]["Amount"]
        console.print(f"  GET /balances → ${bal['Amount']} {bal['Currency']}")

        # 1f. Negative: account NOT in consent.
        if len(accounts) > 1 or True:
            # Try a random account id (Bob's). Use any uuid the consent didn't grant.
            bob_tok = (await c.post("/auth/token", data={"username": "bob@example.com", "password": "ChangeMe-DemoPw#2025"})).json()["access_token"]
            bob_accs = (await c.get("/accounts/me", headers={"Authorization": f"Bearer {bob_tok}"})).json()
            r = await c.get(
                f"/open-banking/v4.0/aisp/accounts/{bob_accs[0]['id']}/balances",
                headers={"Authorization": f"Bearer {aisp_tok}"},
            )
            console.print(f"  Out-of-scope account read → {r.status_code} (expected 403)")

        console.rule("[bold cyan]2. PISP — ZippyPay initiates a payment")

        # 2a. PISP gets a client_credentials token.
        r = await c.post(
            "/open-banking/oauth/token",
            data={"grant_type": "client_credentials", "scope": "payments"},
            headers=basic("zippy-pisp", "zippy-secret-001"),
        )
        pisp_cc_tok = r.json()["access_token"]

        # 2b. Create a payment consent: pay $250 from PSU to Bob.
        r = await c.post(
            "/open-banking/v4.0/pisp/domestic-payment-consents",
            json={
                "Data": {
                    "Initiation": {
                        "InstructionIdentification": "instr-001",
                        "EndToEndIdentification": "e2e-001",
                        "InstructedAmount": {"Amount": "250.00", "Currency": "USD"},
                        "CreditorAccount": {
                            "SchemeName": "UK.AGENTIC.AccountUUID",
                            "Identification": bob_accs[0]["id"],
                            "Name": "Bob Customer",
                        },
                    }
                },
                "Risk": {"PaymentContextCode": "PartyToParty"},
            },
            headers={"Authorization": f"Bearer {pisp_cc_tok}"},
        )
        pay_consent_id = r.json()["Data"]["ConsentId"]
        console.print(f"  PISP consent created: {pay_consent_id}")

        # 2c. PSU authorises, choosing the debtor account.
        r = await c.post(
            "/open-banking/oauth/authorise-consent",
            json={
                "consent_id": pay_consent_id,
                "consent_type": "pisp",
                "debtor_account_id": accounts[0]["id"],
            },
            headers={"Authorization": f"Bearer {psu_tok}"},
        )
        console.print(f"  PSU authorised payment consent: status={r.json()['status']}")

        # 2d. Bind token + submit payment.
        r = await c.post(
            "/open-banking/oauth/token",
            data={"grant_type": "intent", "consent_id": pay_consent_id, "scope": "payments"},
            headers=basic("zippy-pisp", "zippy-secret-001"),
        )
        pisp_tok = r.json()["access_token"]
        r = await c.post(
            "/open-banking/v4.0/pisp/domestic-payments",
            json={
                "Data": {
                    "ConsentId": pay_consent_id,
                    "Initiation": {
                        "InstructionIdentification": "instr-001",
                        "EndToEndIdentification": "e2e-001",
                        "InstructedAmount": {"Amount": "250.00", "Currency": "USD"},
                        "CreditorAccount": {
                            "SchemeName": "UK.AGENTIC.AccountUUID",
                            "Identification": bob_accs[0]["id"],
                            "Name": "Bob Customer",
                        },
                    },
                },
                "Risk": {"PaymentContextCode": "PartyToParty"},
            },
            headers={"Authorization": f"Bearer {pisp_tok}"},
        )
        body = r.json().get("Data", {})
        console.print(f"  payment submitted → status={r.status_code}, OBIE Status={body.get('Status')}")

        # 2e. PISP tries to reuse the consent (must fail — it's Consumed).
        r = await c.post(
            "/open-banking/v4.0/pisp/domestic-payments",
            json={
                "Data": {
                    "ConsentId": pay_consent_id,
                    "Initiation": {
                        "InstructionIdentification": "instr-001",
                        "EndToEndIdentification": "e2e-001",
                        "InstructedAmount": {"Amount": "250.00", "Currency": "USD"},
                        "CreditorAccount": {
                            "SchemeName": "UK.AGENTIC.AccountUUID",
                            "Identification": bob_accs[0]["id"],
                        },
                    },
                },
                "Risk": {},
            },
            headers={"Authorization": f"Bearer {pisp_tok}"},
        )
        console.print(f"  consent re-use attempt → {r.status_code} (expected 403, consent is Consumed)")

        console.rule("[bold cyan]Done")
        console.print("Open http://localhost:16686 to view OTel traces of these flows.")


if __name__ == "__main__":
    asyncio.run(main())
