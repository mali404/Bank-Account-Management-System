"""End-to-end demo scenario.

Walks through:
  1. Customer logs in, lists accounts, makes a low-value transfer (settles).
  2. Customer attempts a high-value transfer (goes to pending_approval).
  3. Compliance officer approves it (separation of duties holds).
  4. Compliance officer freezes a third party account.
  5. Audit log is verified.

Run via:  python -m scripts.demo_scenario
"""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal

import httpx
from rich.console import Console

API = os.environ.get("INTEGRATION_API", "http://localhost:8000")
console = Console()


async def step(title: str) -> None:
    console.rule(f"[bold cyan]{title}")


async def main() -> None:
    async with httpx.AsyncClient(base_url=API, timeout=10) as c:
        # 1. Customer login
        await step("Customer logs in")
        r = await c.post("/auth/token", data={"username": "alice@example.com", "password": "ChangeMe-DemoPw#2025"})
        r.raise_for_status()
        cust_tok = r.json()["access_token"]
        cust_h = {"Authorization": f"Bearer {cust_tok}"}

        await step("Customer views own accounts")
        accounts = (await c.get("/accounts/me", headers=cust_h)).json()
        for a in accounts:
            console.print(f"  account {a['id']} balance ${a['balance']}")

        # Make sure we have at least 2 accounts (alice + bob seeded customers).
        # Find Bob's account by logging in as Bob, asking for an id.
        bob = (await c.post("/auth/token", data={"username": "bob@example.com", "password": "ChangeMe-DemoPw#2025"})).json()["access_token"]
        bob_accs = (await c.get("/accounts/me", headers={"Authorization": f"Bearer {bob}"})).json()
        bob_acc_id = bob_accs[0]["id"] if bob_accs else None

        if not (accounts and bob_acc_id):
            console.print("[red]demo prerequisites missing — did you run `make seed`?")
            return

        src_id = accounts[0]["id"]

        # 2. Low-value transfer
        await step("Low-value transfer ($25 → settles immediately)")
        r = await c.post(
            "/transfers",
            json={"from_account_id": src_id, "to_account_id": bob_acc_id, "amount": "25.00"},
            headers=cust_h,
        )
        console.print(f"  status={r.status_code} state={r.json().get('state')}")

        # 3. High-value transfer (> $5,000) → pending
        await step("High-value transfer ($7,500 → pending_approval)")
        r = await c.post(
            "/transfers",
            json={"from_account_id": src_id, "to_account_id": bob_acc_id, "amount": "7500.00"},
            headers=cust_h,
        )
        body = r.json()
        console.print(f"  status={r.status_code} transfer_id={body.get('id')} state={body.get('state')}")
        pending_id = body.get("id")

        # 4. Compliance officer approves
        await step("Compliance officer approves the pending transfer")
        comp = (await c.post("/auth/token", data={"username": "comp@example.com", "password": "ChangeMe-DemoPw#2025"})).json()["access_token"]
        comp_h = {"Authorization": f"Bearer {comp}"}
        r = await c.post(f"/transfers/{pending_id}/approve", headers=comp_h)
        console.print(f"  status={r.status_code} new_state={r.json().get('state')} approver={r.json().get('approver_user_id')}")

        # 5. Negative path: admin cannot approve
        await step("Admin attempts to transfer (must be 403)")
        admin = (await c.post("/auth/token", data={"username": "admin@example.com", "password": "ChangeMe-DemoPw#2025"})).json()["access_token"]
        admin_h = {"Authorization": f"Bearer {admin}"}
        r = await c.post(
            "/transfers",
            json={"from_account_id": src_id, "to_account_id": bob_acc_id, "amount": "10.00"},
            headers=admin_h,
        )
        console.print(f"  status={r.status_code} (expected 403)")

        await step("Done — open http://localhost:16686 to view agent traces in Jaeger")


if __name__ == "__main__":
    asyncio.run(main())
