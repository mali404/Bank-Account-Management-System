"""Switch usage-rule validator: SLEV, one-tx, date, participant, charset."""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime

import pytest

from agentbank_iso import builders as B
from agentbank_iso import inject
from agentbank_iso import models as M
from agentbank_iso.usage_rules import UsageRuleValidator

SETTLE = date(2026, 10, 29)
NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
UETR = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _payment(**over: object) -> M.Pacs008Payment:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        end_to_end_id="E",
        uetr=UETR,
        amount_minor=100,
        settlement_date=SETTLE,
        debtor_name="Alice",
        debtor_account="1",
        debtor_agent="999900022",
        creditor_name="Landlord",
        creditor_account="2",
        creditor_agent="999900011",
    )
    base.update(over)
    return M.Pacs008Payment(**base)  # type: ignore[arg-type]


@pytest.fixture
def validator() -> UsageRuleValidator:
    return UsageRuleValidator.from_config(clock=lambda: SETTLE)


def _rules(result: object) -> set[str]:
    return {i.rule for i in result.issues}  # type: ignore[attr-defined]


def test_version_is_one(validator: UsageRuleValidator) -> None:
    assert validator.version == 1


def test_valid_payment_passes(validator: UsageRuleValidator) -> None:
    xml = B.build_pacs008(_payment(remittance=("Rent for May",)))
    result = validator.validate(xml, "pacs.008.001.08")
    assert result.ok, [i.__dict__ for i in result.issues]


def test_charge_bearer_must_be_slev(validator: UsageRuleValidator) -> None:
    xml = B.build_pacs008(_payment()).replace(b"<ChrgBr>SLEV</ChrgBr>", b"<ChrgBr>SHAR</ChrgBr>")
    result = validator.validate(xml, "pacs.008.001.08")
    assert "usage:chargeBearer" in _rules(result)


def test_one_tx_per_message(validator: UsageRuleValidator) -> None:
    xml = B.build_pacs008(_payment())
    start = xml.index(b"<CdtTrfTxInf>")
    end = xml.index(b"</CdtTrfTxInf>") + len(b"</CdtTrfTxInf>")
    block = xml[start:end]
    doubled = xml[:end] + block + xml[end:]
    result = validator.validate(doubled, "pacs.008.001.08")
    assert "usage:maxTx" in _rules(result)


def test_settlement_date_must_be_today() -> None:
    validator = UsageRuleValidator.from_config(clock=lambda: date(2000, 1, 1))
    xml = B.build_pacs008(_payment())
    result = validator.validate(xml, "pacs.008.001.08")
    assert "usage:settlementDate" in _rules(result)


def test_routing_must_be_participant(validator: UsageRuleValidator) -> None:
    xml = B.build_pacs008(_payment(debtor_agent="999900099"))
    result = validator.validate(xml, "pacs.008.001.08")
    assert "usage:routing" in _rules(result)


def test_routing_must_be_nine_digits(validator: UsageRuleValidator) -> None:
    xml = B.build_pacs008(_payment()).replace(b"<MmbId>999900022</MmbId>", b"<MmbId>12AB</MmbId>")
    result = validator.validate(xml, "pacs.008.001.08")
    assert "usage:routing" in _rules(result)


def test_currency_must_be_usd(validator: UsageRuleValidator) -> None:
    xml = B.build_pacs008(_payment()).replace(b'Ccy="USD"', b'Ccy="EUR"')
    result = validator.validate(xml, "pacs.008.001.08")
    assert "usage:currency" in _rules(result)


@pytest.mark.parametrize("payload", ["homoglyph", "tag", "bidi"])
def test_latin_profile_blocks_unicode_tricks(validator: UsageRuleValidator, payload: str) -> None:
    name = {
        "homoglyph": inject.homoglyph("Landlord"),
        "tag": "Pay" + inject.tag_smuggle("now"),
        "bidi": inject.bidi_wrap("Landlord", "rlo"),
    }[payload]
    xml = B.build_pacs008(_payment(creditor_name=name))
    result = validator.validate(xml, "pacs.008.001.08")
    assert "usage:charset" in _rules(result)


@pytest.mark.parametrize("payload", ["homoglyph", "tag", "bidi"])
def test_extended_profile_allows_unicode_tricks(payload: str) -> None:
    config = copy.deepcopy(UsageRuleValidator.from_config()._config)
    config["messages"]["pacs.008.001.08"]["charset_profile"] = "extended"
    validator = UsageRuleValidator(
        config=config,
        participants=frozenset({"999900011", "999900022", "999900033"}),
        clock=lambda: SETTLE,
    )
    name = {
        "homoglyph": inject.homoglyph("Landlord"),
        "tag": "Pay" + inject.tag_smuggle("now"),
        "bidi": inject.bidi_wrap("Landlord", "rlo"),
    }[payload]
    xml = B.build_pacs008(_payment(creditor_name=name))
    result = validator.validate(xml, "pacs.008.001.08")
    assert "usage:charset" not in _rules(result)
