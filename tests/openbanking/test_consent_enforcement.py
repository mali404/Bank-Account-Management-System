"""Unit tests for consent enforcement.

These verify the structural properties of authorize_aisp_request and
authorize_pisp_request without spinning up a database — we use a small
fake session that returns a fabricated consent row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.openbanking.consent_service import (
    authorize_aisp_request,
    authorize_pisp_request,
)


@dataclass
class FakeTPP:
    id: Any = field(default_factory=uuid4)
    client_id: str = "test-tpp"


@dataclass
class FakeAACConsent:
    id: str
    tpp_id: Any
    status: str = "Authorised"
    permissions: list[str] = field(default_factory=lambda: ["ReadAccountsBasic"])
    account_ids: list[str] = field(default_factory=list)
    expiration_at: datetime | None = None
    transaction_from: datetime | None = None
    transaction_to: datetime | None = None
    status_updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FakeDPCConsent:
    id: str
    tpp_id: Any
    status: str = "Authorised"
    instructed_amount: Decimal = Decimal("100.00")
    currency: str = "GBP"
    debtor_account_id: Any | None = None
    creditor_scheme: str = "UK.OBIE.SortCodeAccountNumber"
    creditor_identification: str = "11223334445555"
    creditor_name: str | None = "Test Payee"
    instruction_id: str | None = None
    end_to_end_id: str | None = None
    status_updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeSession:
    """Returns a preconfigured row regardless of the query."""

    def __init__(self, row: Any) -> None:
        self._row = row

    async def execute(self, *_a: Any, **_kw: Any) -> FakeResult:
        return FakeResult(self._row)


# --- AISP tests ---------------------------------------------------------


@pytest.mark.unit
async def test_aisp_accepts_matching_consent() -> None:
    tpp = FakeTPP()
    consent = FakeAACConsent(
        id="aac-1",
        tpp_id=tpp.id,
        permissions=["ReadAccountsBasic", "ReadBalances"],
        account_ids=["acc-1"],
    )
    out = await authorize_aisp_request(
        FakeSession(consent),  # type: ignore[arg-type]
        consent_id="aac-1",
        tpp=tpp,  # type: ignore[arg-type]
        required_permission="ReadBalances",
        account_id="acc-1",
    )
    assert out is consent


@pytest.mark.unit
async def test_aisp_rejects_wrong_tpp() -> None:
    consent = FakeAACConsent(id="aac-1", tpp_id=uuid4())
    other_tpp = FakeTPP()
    with pytest.raises(Exception) as exc:
        await authorize_aisp_request(
            FakeSession(consent),  # type: ignore[arg-type]
            consent_id="aac-1",
            tpp=other_tpp,  # type: ignore[arg-type]
            required_permission="ReadAccountsBasic",
        )
    assert "403" in str(exc.value) or "NotAuthorised" in str(exc.value.args)


@pytest.mark.unit
async def test_aisp_rejects_unauthorised_status() -> None:
    tpp = FakeTPP()
    consent = FakeAACConsent(id="aac-1", tpp_id=tpp.id, status="Revoked")
    with pytest.raises(Exception):
        await authorize_aisp_request(
            FakeSession(consent),  # type: ignore[arg-type]
            consent_id="aac-1",
            tpp=tpp,  # type: ignore[arg-type]
            required_permission="ReadAccountsBasic",
        )


@pytest.mark.unit
async def test_aisp_rejects_missing_permission() -> None:
    tpp = FakeTPP()
    consent = FakeAACConsent(
        id="aac-1",
        tpp_id=tpp.id,
        permissions=["ReadAccountsBasic"],  # no ReadBalances
    )
    with pytest.raises(Exception):
        await authorize_aisp_request(
            FakeSession(consent),  # type: ignore[arg-type]
            consent_id="aac-1",
            tpp=tpp,  # type: ignore[arg-type]
            required_permission="ReadBalances",
        )


@pytest.mark.unit
async def test_aisp_rejects_out_of_scope_account() -> None:
    tpp = FakeTPP()
    consent = FakeAACConsent(
        id="aac-1",
        tpp_id=tpp.id,
        permissions=["ReadAccountsBasic"],
        account_ids=["acc-1"],
    )
    with pytest.raises(Exception):
        await authorize_aisp_request(
            FakeSession(consent),  # type: ignore[arg-type]
            consent_id="aac-1",
            tpp=tpp,  # type: ignore[arg-type]
            required_permission="ReadAccountsBasic",
            account_id="acc-99",
        )


@pytest.mark.unit
async def test_aisp_rejects_expired_consent() -> None:
    tpp = FakeTPP()
    consent = FakeAACConsent(
        id="aac-1",
        tpp_id=tpp.id,
        permissions=["ReadAccountsBasic"],
        expiration_at=datetime.now(UTC) - timedelta(days=1),
    )
    with pytest.raises(Exception):
        await authorize_aisp_request(
            FakeSession(consent),  # type: ignore[arg-type]
            consent_id="aac-1",
            tpp=tpp,  # type: ignore[arg-type]
            required_permission="ReadAccountsBasic",
        )


# --- PISP tests ---------------------------------------------------------


@pytest.mark.unit
async def test_pisp_accepts_authorised_consent() -> None:
    tpp = FakeTPP()
    consent = FakeDPCConsent(id="dpc-1", tpp_id=tpp.id, status="Authorised")
    out = await authorize_pisp_request(
        FakeSession(consent),  # type: ignore[arg-type]
        consent_id="dpc-1",
        tpp=tpp,  # type: ignore[arg-type]
    )
    assert out is consent


@pytest.mark.unit
async def test_pisp_rejects_consumed_when_authorised_expected() -> None:
    tpp = FakeTPP()
    consent = FakeDPCConsent(id="dpc-1", tpp_id=tpp.id, status="Consumed")
    with pytest.raises(Exception):
        await authorize_pisp_request(
            FakeSession(consent),  # type: ignore[arg-type]
            consent_id="dpc-1",
            tpp=tpp,  # type: ignore[arg-type]
            expected_state="Authorised",
        )
