"""Free-text length limits: each attacker-controllable field accepts its XSD
maximum and rejects one more character, with the right field path reported.

The limits come from each message's real XSD ``maxLength`` (see the registry in
``agentbank_iso.messages`` and the table in the library README): names/Ustrd are
140, ``AddtlInf`` is 105, ``AddtlNtryInf`` is 500, ``RsnDesc`` is 350.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest

from agentbank_iso import builders as B
from agentbank_iso import models as M
from agentbank_iso.errors import FieldLengthError
from agentbank_iso.messages import iter_specs
from agentbank_iso.validate import validate_xsd

NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
DAY = date(2026, 10, 29)
UETR = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
R1, R2 = "999900022", "999900011"

# For each (message_id, field label): a function text -> serialised bytes.
FIELD_BUILDERS: dict[tuple[str, str], Callable[[str], bytes]] = {
    ("pacs.008.001.08", "Dbtr/Nm"): lambda t: B.build_pacs008(_pacs008(debtor_name=t)),
    ("pacs.008.001.08", "Cdtr/Nm"): lambda t: B.build_pacs008(_pacs008(creditor_name=t)),
    ("pacs.008.001.08", "UltmtDbtr/Nm"): lambda t: B.build_pacs008(
        _pacs008(ultimate_debtor_name=t)
    ),
    ("pacs.008.001.08", "RmtInf/Ustrd"): lambda t: B.build_pacs008(_pacs008(remittance=(t,))),
    ("pacs.008.001.08", "RmtInf/Strd/AddtlRmtInf"): lambda t: B.build_pacs008(
        _pacs008(addtl_rmt_inf=(t,))
    ),
    ("pacs.008.001.08", "InstrForCdtrAgt/InstrInf"): lambda t: B.build_pacs008(
        _pacs008(instr_for_cdtr_agt=t)
    ),
    ("pacs.002.001.10", "StsRsnInf/AddtlInf"): lambda t: B.build_pacs002(
        _pacs002(status_reason_addtl=(t,))
    ),
    ("pacs.004.001.10", "RtrRsnInf/AddtlInf"): lambda t: B.build_pacs004(
        _pacs004(return_reason_addtl=(t,))
    ),
    ("camt.056.001.08", "CxlRsnInf/AddtlInf"): lambda t: B.build_camt056(
        _camt056(cancellation_reason_addtl=(t,))
    ),
    ("camt.029.001.09", "CxlStsRsnInf/AddtlInf"): lambda t: B.build_camt029(
        _camt029(cancellation_status_reason_addtl=(t,))
    ),
    ("pain.013.001.07", "Cdtr/Nm"): lambda t: B.build_pain013(_pain013(creditor_name=t)),
    ("pain.013.001.07", "RmtInf/Ustrd"): lambda t: B.build_pain013(_pain013(remittance=(t,))),
    ("pain.013.001.07", "InstrForCdtrAgt/InstrInf"): lambda t: B.build_pain013(
        _pain013(instr_for_cdtr_agt=t)
    ),
    ("pain.014.001.07", "StsRsnInf/AddtlInf"): lambda t: B.build_pain014(
        _pain014(status_reason_addtl=(t,))
    ),
    ("pain.001.001.09", "Cdtr/Nm"): lambda t: B.build_pain001(_pain001(creditor_name=t)),
    ("pain.001.001.09", "RmtInf/Ustrd"): lambda t: B.build_pain001(_pain001(remittance=(t,))),
    ("pain.002.001.10", "StsRsnInf/AddtlInf"): lambda t: B.build_pain002(
        _pain002(status_reason_addtl=(t,))
    ),
    ("camt.053.001.08", "Ntry/AddtlNtryInf"): lambda t: B.build_camt053(
        _camt053(M.Entry(100, "CRDT", additional_entry_info=t))
    ),
    ("camt.053.001.08", "NtryDtls/TxDtls/RmtInf/Ustrd"): lambda t: B.build_camt053(
        _camt053(M.Entry(100, "CRDT", remittance=(t,)))
    ),
    ("camt.054.001.08", "Ntry/AddtlNtryInf"): lambda t: B.build_camt054(
        _camt054(M.Entry(100, "CRDT", additional_entry_info=t))
    ),
    ("camt.054.001.08", "NtryDtls/TxDtls/RmtInf/Ustrd"): lambda t: B.build_camt054(
        _camt054(M.Entry(100, "CRDT", remittance=(t,)))
    ),
    ("camt.052.001.08", "Ntry/AddtlNtryInf"): lambda t: B.build_camt052(
        _camt052(M.Entry(100, "CRDT", additional_entry_info=t))
    ),
    ("admi.002.001.01", "Rsn/RsnDesc"): lambda t: B.build_admi002(_admi002(reason_description=t)),
}


def _pacs008(**over: object) -> M.Pacs008Payment:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        end_to_end_id="E",
        uetr=UETR,
        amount_minor=100,
        settlement_date=DAY,
        debtor_name="A",
        debtor_account="1",
        debtor_agent=R1,
        creditor_name="B",
        creditor_account="2",
        creditor_agent=R2,
    )
    base.update(over)
    return M.Pacs008Payment(**base)  # type: ignore[arg-type]


def _pacs002(**over: object) -> M.Pacs002Status:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        orgnl_msg_id="O",
        orgnl_msg_nm_id="pacs.008.001.08",
        orgnl_end_to_end_id="E",
        orgnl_uetr=UETR,
        tx_status="ACSC",
    )
    base.update(over)
    return M.Pacs002Status(**base)  # type: ignore[arg-type]


def _pacs004(**over: object) -> M.Pacs004Return:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        orgnl_msg_id="O",
        orgnl_msg_nm_id="pacs.008.001.08",
        orgnl_end_to_end_id="E",
        orgnl_uetr=UETR,
        returned_amount_minor=100,
        settlement_date=DAY,
    )
    base.update(over)
    return M.Pacs004Return(**base)  # type: ignore[arg-type]


def _camt056(**over: object) -> M.Camt056CancellationRequest:
    base: dict[str, object] = dict(
        assignment_id="A",
        created_at=NOW,
        assigner_routing=R1,
        assignee_routing=R2,
        case_id="C",
        orgnl_msg_id="O",
        orgnl_msg_nm_id="pacs.008.001.08",
        orgnl_end_to_end_id="E",
        orgnl_uetr=UETR,
    )
    base.update(over)
    return M.Camt056CancellationRequest(**base)  # type: ignore[arg-type]


def _camt029(**over: object) -> M.Camt029Resolution:
    base: dict[str, object] = dict(
        assignment_id="A",
        created_at=NOW,
        assigner_routing=R1,
        assignee_routing=R2,
        status_confirmation="CNCL",
        orgnl_end_to_end_id="E",
        orgnl_uetr=UETR,
    )
    base.update(over)
    return M.Camt029Resolution(**base)  # type: ignore[arg-type]


def _pain013(**over: object) -> M.Pain013Rfp:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        initiating_party="P",
        pmt_inf_id="PI",
        end_to_end_id="E",
        amount_minor=100,
        execution_date=DAY,
        debtor_name="A",
        debtor_agent=R1,
        creditor_name="B",
        creditor_agent=R2,
    )
    base.update(over)
    return M.Pain013Rfp(**base)  # type: ignore[arg-type]


def _pain014(**over: object) -> M.Pain014RfpStatus:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        initiating_party="P",
        orgnl_msg_id="O",
        orgnl_msg_nm_id="pain.013.001.07",
        orgnl_pmt_inf_id="PI",
        orgnl_end_to_end_id="E",
        tx_status="ACCP",
    )
    base.update(over)
    return M.Pain014RfpStatus(**base)  # type: ignore[arg-type]


def _pain001(**over: object) -> M.Pain001Initiation:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        initiating_party="P",
        pmt_inf_id="PI",
        end_to_end_id="E",
        amount_minor=100,
        execution_date=DAY,
        debtor_name="A",
        debtor_account="1",
        debtor_agent=R1,
        creditor_name="B",
        creditor_account="2",
        creditor_agent=R2,
    )
    base.update(over)
    return M.Pain001Initiation(**base)  # type: ignore[arg-type]


def _pain002(**over: object) -> M.Pain002Status:
    base: dict[str, object] = dict(
        msg_id="M",
        created_at=NOW,
        orgnl_msg_id="O",
        orgnl_msg_nm_id="pain.001.001.09",
        orgnl_pmt_inf_id="PI",
        orgnl_end_to_end_id="E",
        tx_status="ACSP",
    )
    base.update(over)
    return M.Pain002Status(**base)  # type: ignore[arg-type]


def _camt053(entry: M.Entry) -> M.Camt053Statement:
    return M.Camt053Statement("M", NOW, "S", "ACC", entries=(entry,))


def _camt054(entry: M.Entry) -> M.Camt054Notification:
    return M.Camt054Notification("M", NOW, "N", "ACC", entries=(entry,))


def _camt052(entry: M.Entry) -> M.Camt052Report:
    return M.Camt052Report("M", NOW, "R", "ACC", entries=(entry,))


def _admi002(**over: object) -> M.Admi002Reject:
    base: dict[str, object] = dict(related_ref="R", rejecting_party_reason="X01")
    base.update(over)
    return M.Admi002Reject(**base)  # type: ignore[arg-type]


# Build the parameter list from the registry so every §6.1 free-text field is covered.
_PARAMS = [
    (spec.message_id, fld.label, fld.path, fld.max_length)
    for spec in iter_specs()
    for fld in spec.free_text_fields
]


def test_registry_fields_all_have_builders() -> None:
    for message_id, label, _path, _max in _PARAMS:
        assert (message_id, label) in FIELD_BUILDERS, (message_id, label)


@pytest.mark.parametrize(
    ("message_id", "label", "path", "max_length"),
    _PARAMS,
    ids=[f"{m}:{lbl}" for m, lbl, _p, _n in _PARAMS],
)
def test_at_limit_accepted(message_id: str, label: str, path: str, max_length: int) -> None:
    build = FIELD_BUILDERS[(message_id, label)]
    xml = build("Z" * max_length)
    result = validate_xsd(xml, message_id)
    assert result.ok, [i.__dict__ for i in result.issues]


@pytest.mark.parametrize(
    ("message_id", "label", "path", "max_length"),
    _PARAMS,
    ids=[f"{m}:{lbl}" for m, lbl, _p, _n in _PARAMS],
)
def test_over_limit_builder_refuses(
    message_id: str, label: str, path: str, max_length: int
) -> None:
    build = FIELD_BUILDERS[(message_id, label)]
    with pytest.raises(FieldLengthError):
        build("Z" * (max_length + 1))


@pytest.mark.parametrize(
    ("message_id", "label", "path", "max_length"),
    _PARAMS,
    ids=[f"{m}:{lbl}" for m, lbl, _p, _n in _PARAMS],
)
def test_over_limit_validator_reports_path(
    message_id: str, label: str, path: str, max_length: int
) -> None:
    build = FIELD_BUILDERS[(message_id, label)]
    at_limit = build("Z" * max_length)
    over = at_limit.replace(b"Z" * max_length, b"Z" * (max_length + 1))
    result = validate_xsd(over, message_id)
    assert not result.ok
    matches = [i for i in result.issues if i.path == path and i.rule == "xsd:maxLength"]
    assert matches, (path, [(i.path, i.rule) for i in result.issues])
