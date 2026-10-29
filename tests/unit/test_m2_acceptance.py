"""M2 acceptance: a payment settles, the books stay consistent, reset is fast."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from agentbank_ledger.api import create_bank_app
from agentbank_ledger.seed import seed_world
from agentbank_ledger.simnow import SwitchReply
from agentbank_ledger.world import World, restore_tree

AMOUNT = 185_000  # $1,850.00


def _fund(world: World) -> tuple[str, str]:
    debtor_bank = world.bank("bank-b")
    creditor_bank = world.bank("bank-a")
    debtor_bank.add_customer("Alice Example", "alice@bank-b.test")
    creditor_bank.add_customer("Landlord Example", "landlord@bank-a.test")
    debtor = debtor_bank.add_account("alice@bank-b.test", "DDA", "200000001")
    creditor = creditor_bank.add_account("landlord@bank-a.test", "DDA", "100000001")
    debtor_bank.deposit(debtor, 1_000_000, "OPENING")
    creditor_bank.deposit(creditor, 1_000_000, "OPENING")
    return debtor, "100000001"


def _pay(world: World, debtor: str, creditor_number: str, amount: int = AMOUNT) -> SwitchReply:
    return world.bank("bank-b").send_interbank(
        debtor,
        "Landlord Example",
        creditor_number,
        world.bank("bank-a").routing,
        amount,
        remittance=("RENT",),
        principal="alice@bank-b.test",
    )


def test_payment_settles_under_two_seconds(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    before_debtor = world.bank("bank-b").available(debtor)
    before_creditor = world.bank("bank-a").available("bank-a:100000001")
    reply = _pay(world, debtor, creditor_number)
    assert reply.tx_status == "ACSC", reply.detail
    assert reply.elapsed_s < 2
    assert world.bank("bank-b").available(debtor) == before_debtor - AMOUNT
    assert world.bank("bank-a").available("bank-a:100000001") == before_creditor + AMOUNT
    assert world.check_invariants() == []
    assert any(item.startswith("simnow.to_switch.") for item in world.switch.trace)
    assert any(item.startswith("simnow.to_bank.") for item in world.switch.trace)
    assert world.bank("bank-a").notifications()


def test_duplicate_envelope_rejected(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    reply = _pay(world, debtor, creditor_number)
    assert reply.tx_status == "ACSC"
    envelope = next(item.xml for item in world.switch.archive if b"pacs.008" in item.xml)
    balance = world.bank("bank-a").available("bank-a:100000001")
    again = world.switch.submit(envelope)
    assert again.tx_status == "RJCT"
    assert again.reason_code == "AM05"
    assert world.bank("bank-a").available("bank-a:100000001") == balance
    assert world.check_invariants() == []


def test_participant_limit_rejects_without_moving_funds(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    world.switch.limits[world.bank("bank-b").routing] = 1_000
    before = world.bank("bank-b").available(debtor)
    reply = _pay(world, debtor, creditor_number, amount=2_000)
    assert reply.tx_status == "RJCT"
    assert reply.reason_code == "AM02"
    assert world.bank("bank-b").available(debtor) == before
    assert world.settlement.pending_debit(world.bank("bank-b").routing) == 0
    assert world.check_invariants() == []


def test_timeout_voids_the_pending_transfer(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    world.bank("bank-a").response_delay_s = 30
    assert world.switch.timeout_s == 20
    before = world.bank("bank-b").available(debtor)
    reply = _pay(world, debtor, creditor_number)
    assert reply.tx_status == "RJCT"
    assert reply.reason_code == "AB05"
    assert world.bank("bank-b").available(debtor) == before
    assert world.settlement.pending_debit(world.bank("bank-b").routing) == 0
    assert world.check_invariants() == []


def test_return_restores_both_banks(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    debtor_before = world.bank("bank-b").available(debtor)
    creditor_before = world.bank("bank-a").available("bank-a:100000001")
    position_b = world.settlement.position(world.bank("bank-b").routing)
    position_a = world.settlement.position(world.bank("bank-a").routing)
    reply = _pay(world, debtor, creditor_number)
    assert reply.tx_status == "ACSC"
    rows = world.bank("bank-b").books.payments_rows()
    outbound = next(row for row in rows if row["direction"] == "out")
    returned = world.bank("bank-b").request_return(str(outbound["uetr"]))
    assert returned.tx_status == "ACSC", returned.detail
    assert world.bank("bank-b").available(debtor) == debtor_before
    assert world.bank("bank-a").available("bank-a:100000001") == creditor_before
    assert world.settlement.position(world.bank("bank-b").routing) == position_b
    assert world.settlement.position(world.bank("bank-a").routing) == position_a
    assert world.check_invariants() == []


def test_hash_chain_detects_tampering(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    assert _pay(world, debtor, creditor_number).tx_status == "ACSC"
    assert world.switch.hash_chain_ok()
    world.switch.archive[0].xml = b"<tampered/>"
    assert world.switch.hash_chain_ok() is False


def test_request_for_payment_is_forwarded(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    sent = world.bank("bank-a").send_rfp(
        "Landlord Example",
        "Alice Example",
        world.bank("bank-b").routing,
        5_000,
        remittance=("RENT",),
    )
    assert sent.tx_status == "ACSC", sent.detail
    inbox = world.bank("bank-b").rfp_inbox()
    assert len(inbox) == 1
    end_to_end_id = str(inbox[0]["end_to_end_id"])
    status = world.bank("bank-b").respond_rfp(end_to_end_id, True)
    assert status.tx_status == "ACSC", status.detail
    paid = world.bank("bank-b").pay_rfp(end_to_end_id, debtor, creditor_number)
    assert paid.tx_status == "ACSC", paid.detail
    assert world.check_invariants() == []


def test_reset_restores_the_snapshot_quickly(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    world.mark_snapshot()
    before = world.canonical()
    assert _pay(world, debtor, creditor_number).tx_status == "ACSC"
    assert world.canonical() != before
    elapsed = world.reset()
    assert elapsed < 30
    assert world.canonical() == before
    assert world.check_invariants() == []
    world.mark_snapshot()
    file_elapsed = restore_tree(tmp_path)
    assert file_elapsed < 30


def test_seed_is_deterministic(tmp_path: Path) -> None:
    first = World.create(tmp_path / "a")
    second = World.create(tmp_path / "b")
    left = seed_world(first, 42)
    right = seed_world(second, 42)
    assert left["canonical_sha256"] == right["canonical_sha256"]
    assert left["counts"]["customers"] == 150
    assert hashlib.sha256(first.canonical()).hexdigest() == left["canonical_sha256"]
    assert first.check_invariants() == []


def test_app_and_ops_http(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    debtor, creditor_number = _fund(world)
    client = TestClient(create_bank_app(world.bank("bank-b")))
    denied = client.get("/app/v1/accounts")
    assert denied.status_code == 401
    headers = {"X-Customer-Id": "alice@bank-b.test"}
    accounts = client.get("/app/v1/accounts", headers=headers)
    assert accounts.status_code == 200
    assert accounts.json()[0]["accountId"] == debtor
    paid = client.post(
        "/app/v1/payments",
        headers=headers,
        json={
            "debtor_account_id": debtor,
            "creditor_name": "Landlord Example",
            "creditor_account": creditor_number,
            "creditor_routing": world.bank("bank-a").routing,
            "amount_minor": 4_200,
            "remittance": ["RENT"],
        },
    )
    assert paid.status_code == 200
    assert paid.json()["txStatus"] == "ACSC"
    staff = {"X-Staff-Id": "ops1@bank-b.test"}
    profile = client.get("/ops/v1/customers/alice@bank-b.test", headers=staff)
    assert profile.status_code == 200
    assert profile.json()["name"] == "Alice Example"
    assert client.get("/healthz").json()["bank"] == "bank-b"
