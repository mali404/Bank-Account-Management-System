"""Hypothesis strategies producing valid ISO 20022 domain models.

Each ``RoundTripCase`` pairs a message id with a model strategy and the matching
build/parse functions, so the round-trip test can parametrize over the whole
SPEC §6.1 set. Free-text values draw from a safe printable alphabet (no control
or boundary-whitespace characters) so that build → parse is byte-stable; the
Unicode-trick payloads are exercised separately by the inject tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from hypothesis import strategies as st

from agentbank_iso import builders as B
from agentbank_iso import models as M
from agentbank_iso import parsers as P

ROUTINGS = ["999900011", "999900022", "999900033"]
_SAFE_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,-/()'+:?éüñáΩ"


def safe_text(min_size: int = 1, max_size: int = 140) -> st.SearchStrategy[str]:
    """Printable text with no boundary whitespace and length in range."""
    return (
        st.text(alphabet=_SAFE_ALPHABET, min_size=min_size, max_size=max_size)
        .map(str.strip)
        .filter(lambda s: min_size <= len(s) <= max_size)
    )


def codes() -> st.SearchStrategy[str]:
    return st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=4)


def ids(max_size: int = 35) -> st.SearchStrategy[str]:
    return st.text(alphabet=_SAFE_ALPHABET.replace(" ", ""), min_size=1, max_size=max_size)


def amounts() -> st.SearchStrategy[int]:
    return st.integers(min_value=1, max_value=10_000_000)


def uetrs() -> st.SearchStrategy[str]:
    return st.uuids(version=4).map(str)


def datetimes() -> st.SearchStrategy[datetime]:
    return st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2035, 12, 31),
        timezones=st.just(UTC),
    ).map(lambda d: d.replace(microsecond=0))


def dates() -> st.SearchStrategy[date]:
    return st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 12, 31))


def names() -> st.SearchStrategy[str]:
    return safe_text(1, 140)


def ustrd_lines(max_lines: int = 3) -> st.SearchStrategy[tuple[str, ...]]:
    return st.lists(safe_text(1, 140), min_size=0, max_size=max_lines).map(tuple)


def addtl_info(max_len: int = 105, max_lines: int = 2) -> st.SearchStrategy[tuple[str, ...]]:
    return st.lists(safe_text(1, max_len), min_size=0, max_size=max_lines).map(tuple)


@st.composite
def pacs008(draw: st.DrawFn) -> M.Pacs008Payment:
    return M.Pacs008Payment(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        end_to_end_id=draw(ids()),
        uetr=draw(uetrs()),
        amount_minor=draw(amounts()),
        settlement_date=draw(dates()),
        debtor_name=draw(names()),
        debtor_account=draw(ids(34)),
        debtor_agent=draw(st.sampled_from(ROUTINGS)),
        creditor_name=draw(names()),
        creditor_account=draw(ids(34)),
        creditor_agent=draw(st.sampled_from(ROUTINGS)),
        remittance=draw(ustrd_lines()),
        ultimate_debtor_name=draw(st.none() | names()),
        instr_for_cdtr_agt=draw(st.none() | safe_text(1, 140)),
        addtl_rmt_inf=draw(st.lists(safe_text(1, 140), max_size=2).map(tuple)),
    )


@st.composite
def pacs002(draw: st.DrawFn) -> M.Pacs002Status:
    return M.Pacs002Status(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        orgnl_msg_id=draw(ids()),
        orgnl_msg_nm_id=draw(st.just("pacs.008.001.08")),
        orgnl_end_to_end_id=draw(ids()),
        orgnl_uetr=draw(uetrs()),
        tx_status=draw(codes()),
        status_reason_code=draw(st.none() | codes()),
        status_reason_addtl=draw(addtl_info()),
    )


@st.composite
def pacs004(draw: st.DrawFn) -> M.Pacs004Return:
    return M.Pacs004Return(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        orgnl_msg_id=draw(ids()),
        orgnl_msg_nm_id=draw(st.just("pacs.008.001.08")),
        orgnl_end_to_end_id=draw(ids()),
        orgnl_uetr=draw(uetrs()),
        returned_amount_minor=draw(amounts()),
        settlement_date=draw(dates()),
        return_reason_code=draw(st.none() | codes()),
        return_reason_addtl=draw(addtl_info()),
    )


@st.composite
def camt056(draw: st.DrawFn) -> M.Camt056CancellationRequest:
    return M.Camt056CancellationRequest(
        assignment_id=draw(ids()),
        created_at=draw(datetimes()),
        assigner_routing=draw(st.sampled_from(ROUTINGS)),
        assignee_routing=draw(st.sampled_from(ROUTINGS)),
        case_id=draw(ids()),
        orgnl_msg_id=draw(ids()),
        orgnl_msg_nm_id=draw(st.just("pacs.008.001.08")),
        orgnl_end_to_end_id=draw(ids()),
        orgnl_uetr=draw(uetrs()),
        cancellation_reason_code=draw(st.none() | codes()),
        cancellation_reason_addtl=draw(addtl_info()),
    )


@st.composite
def camt029(draw: st.DrawFn) -> M.Camt029Resolution:
    return M.Camt029Resolution(
        assignment_id=draw(ids()),
        created_at=draw(datetimes()),
        assigner_routing=draw(st.sampled_from(ROUTINGS)),
        assignee_routing=draw(st.sampled_from(ROUTINGS)),
        status_confirmation=draw(codes()),
        orgnl_end_to_end_id=draw(ids()),
        orgnl_uetr=draw(uetrs()),
        cancellation_status_reason_code=draw(st.none() | codes()),
        cancellation_status_reason_addtl=draw(addtl_info()),
    )


@st.composite
def pacs028(draw: st.DrawFn) -> M.Pacs028StatusRequest:
    return M.Pacs028StatusRequest(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        orgnl_msg_id=draw(ids()),
        orgnl_msg_nm_id=draw(st.just("pacs.008.001.08")),
        orgnl_end_to_end_id=draw(ids()),
        orgnl_uetr=draw(uetrs()),
    )


@st.composite
def pain013(draw: st.DrawFn) -> M.Pain013Rfp:
    return M.Pain013Rfp(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        initiating_party=draw(names()),
        pmt_inf_id=draw(ids()),
        end_to_end_id=draw(ids()),
        amount_minor=draw(amounts()),
        execution_date=draw(dates()),
        debtor_name=draw(names()),
        debtor_agent=draw(st.sampled_from(ROUTINGS)),
        creditor_name=draw(names()),
        creditor_agent=draw(st.sampled_from(ROUTINGS)),
        remittance=draw(ustrd_lines()),
        instr_for_cdtr_agt=draw(st.none() | safe_text(1, 140)),
    )


@st.composite
def pain014(draw: st.DrawFn) -> M.Pain014RfpStatus:
    return M.Pain014RfpStatus(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        initiating_party=draw(names()),
        orgnl_msg_id=draw(ids()),
        orgnl_msg_nm_id=draw(st.just("pain.013.001.07")),
        orgnl_pmt_inf_id=draw(ids()),
        orgnl_end_to_end_id=draw(ids()),
        tx_status=draw(codes()),
        status_reason_code=draw(st.none() | codes()),
        status_reason_addtl=draw(addtl_info()),
    )


@st.composite
def pain001(draw: st.DrawFn) -> M.Pain001Initiation:
    return M.Pain001Initiation(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        initiating_party=draw(names()),
        pmt_inf_id=draw(ids()),
        end_to_end_id=draw(ids()),
        amount_minor=draw(amounts()),
        execution_date=draw(dates()),
        debtor_name=draw(names()),
        debtor_account=draw(ids(34)),
        debtor_agent=draw(st.sampled_from(ROUTINGS)),
        creditor_name=draw(names()),
        creditor_account=draw(ids(34)),
        creditor_agent=draw(st.sampled_from(ROUTINGS)),
        remittance=draw(ustrd_lines()),
    )


@st.composite
def pain002(draw: st.DrawFn) -> M.Pain002Status:
    return M.Pain002Status(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        orgnl_msg_id=draw(ids()),
        orgnl_msg_nm_id=draw(st.just("pain.001.001.09")),
        orgnl_pmt_inf_id=draw(ids()),
        orgnl_end_to_end_id=draw(ids()),
        tx_status=draw(codes()),
        status_reason_code=draw(st.none() | codes()),
        status_reason_addtl=draw(addtl_info()),
    )


@st.composite
def entries(draw: st.DrawFn, with_remittance: bool = True) -> M.Entry:
    return M.Entry(
        amount_minor=draw(amounts()),
        credit_debit=draw(st.sampled_from(["CRDT", "DBIT"])),
        status=draw(st.sampled_from(["BOOK", "PDNG", "INFO"])),
        additional_entry_info=draw(st.none() | safe_text(1, 500)),
        remittance=draw(ustrd_lines()) if with_remittance else (),
    )


@st.composite
def camt053(draw: st.DrawFn) -> M.Camt053Statement:
    return M.Camt053Statement(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        statement_id=draw(ids()),
        account_id=draw(ids(34)),
        entries=draw(st.lists(entries(), min_size=0, max_size=3).map(tuple)),
    )


@st.composite
def camt054(draw: st.DrawFn) -> M.Camt054Notification:
    return M.Camt054Notification(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        notification_id=draw(ids()),
        account_id=draw(ids(34)),
        entries=draw(st.lists(entries(), min_size=0, max_size=3).map(tuple)),
    )


@st.composite
def camt052(draw: st.DrawFn) -> M.Camt052Report:
    return M.Camt052Report(
        msg_id=draw(ids()),
        created_at=draw(datetimes()),
        report_id=draw(ids()),
        account_id=draw(ids(34)),
        entries=draw(st.lists(entries(with_remittance=False), min_size=0, max_size=3).map(tuple)),
    )


@st.composite
def admi002(draw: st.DrawFn) -> M.Admi002Reject:
    return M.Admi002Reject(
        related_ref=draw(ids()),
        rejecting_party_reason=draw(ids()),
        reason_description=draw(st.none() | safe_text(1, 350)),
        error_location=draw(st.none() | safe_text(1, 350)),
    )


@st.composite
def head001(draw: st.DrawFn) -> M.BusinessHeader:
    return M.BusinessHeader(
        from_routing=draw(st.sampled_from(ROUTINGS)),
        to_routing=draw(st.sampled_from(ROUTINGS)),
        biz_msg_idr=draw(ids()),
        msg_def_idr=draw(st.sampled_from(["pacs.008.001.08", "pacs.002.001.10"])),
        created_at=draw(datetimes()),
        biz_svc=draw(st.none() | safe_text(1, 35)),
    )


@dataclass(frozen=True)
class RoundTripCase:
    message_id: str
    strategy: st.SearchStrategy[Any]
    build: Callable[[Any], bytes]
    parse: Callable[[bytes], Any]


ROUND_TRIP_CASES: tuple[RoundTripCase, ...] = (
    RoundTripCase("head.001.001.02", head001(), B.build_head001, P.parse_head001),
    RoundTripCase("pacs.008.001.08", pacs008(), B.build_pacs008, P.parse_pacs008),
    RoundTripCase("pacs.002.001.10", pacs002(), B.build_pacs002, P.parse_pacs002),
    RoundTripCase("pacs.004.001.10", pacs004(), B.build_pacs004, P.parse_pacs004),
    RoundTripCase("camt.056.001.08", camt056(), B.build_camt056, P.parse_camt056),
    RoundTripCase("camt.029.001.09", camt029(), B.build_camt029, P.parse_camt029),
    RoundTripCase("pacs.028.001.03", pacs028(), B.build_pacs028, P.parse_pacs028),
    RoundTripCase("pain.013.001.07", pain013(), B.build_pain013, P.parse_pain013),
    RoundTripCase("pain.014.001.07", pain014(), B.build_pain014, P.parse_pain014),
    RoundTripCase("pain.001.001.09", pain001(), B.build_pain001, P.parse_pain001),
    RoundTripCase("pain.002.001.10", pain002(), B.build_pain002, P.parse_pain002),
    RoundTripCase("camt.053.001.08", camt053(), B.build_camt053, P.parse_camt053),
    RoundTripCase("camt.054.001.08", camt054(), B.build_camt054, P.parse_camt054),
    RoundTripCase("camt.052.001.08", camt052(), B.build_camt052, P.parse_camt052),
    RoundTripCase("admi.002.001.01", admi002(), B.build_admi002, P.parse_admi002),
)
