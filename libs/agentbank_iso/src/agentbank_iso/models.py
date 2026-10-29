"""Typed domain models for the ISO 20022 fields the testbed actually uses.

These are deliberately small frozen dataclasses — far smaller than the full
xsdata bindings — carrying exactly the fields the builders write and the parsers
read back, so a build → parse round trip reconstructs an equal model. Amounts are
integer USD minor units (:mod:`agentbank_common.money`); timestamps are
timezone-aware UTC datetimes; routing numbers are nine-digit participant ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

__all__ = [
    "Admi002Reject",
    "BusinessHeader",
    "Camt029Resolution",
    "Camt052Report",
    "Camt053Statement",
    "Camt054Notification",
    "Camt056CancellationRequest",
    "Entry",
    "Pacs002Status",
    "Pacs004Return",
    "Pacs008Payment",
    "Pacs028StatusRequest",
    "Pain001Initiation",
    "Pain002Status",
    "Pain013Rfp",
    "Pain014RfpStatus",
]


@dataclass(frozen=True)
class BusinessHeader:
    """head.001 Business Application Header (BAH)."""

    from_routing: str
    to_routing: str
    biz_msg_idr: str
    msg_def_idr: str
    created_at: datetime
    biz_svc: str | None = None


@dataclass(frozen=True)
class Pacs008Payment:
    """pacs.008 FIToFICstmrCdtTrf — a single credit transfer."""

    msg_id: str
    created_at: datetime
    end_to_end_id: str
    uetr: str
    amount_minor: int
    settlement_date: date
    debtor_name: str
    debtor_account: str
    debtor_agent: str
    creditor_name: str
    creditor_account: str
    creditor_agent: str
    remittance: tuple[str, ...] = ()
    ultimate_debtor_name: str | None = None
    instr_for_cdtr_agt: str | None = None
    addtl_rmt_inf: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pacs002Status:
    """pacs.002 FIToFIPmtStsRpt — status report for one transaction."""

    msg_id: str
    created_at: datetime
    orgnl_msg_id: str
    orgnl_msg_nm_id: str
    orgnl_end_to_end_id: str
    orgnl_uetr: str
    tx_status: str
    status_reason_code: str | None = None
    status_reason_addtl: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pacs004Return:
    """pacs.004 PmtRtr — return of funds for one transaction."""

    msg_id: str
    created_at: datetime
    orgnl_msg_id: str
    orgnl_msg_nm_id: str
    orgnl_end_to_end_id: str
    orgnl_uetr: str
    returned_amount_minor: int
    settlement_date: date
    return_reason_code: str | None = None
    return_reason_addtl: tuple[str, ...] = ()


@dataclass(frozen=True)
class Camt056CancellationRequest:
    """camt.056 FIToFIPmtCxlReq — a return/recall request."""

    assignment_id: str
    created_at: datetime
    assigner_routing: str
    assignee_routing: str
    case_id: str
    orgnl_msg_id: str
    orgnl_msg_nm_id: str
    orgnl_end_to_end_id: str
    orgnl_uetr: str
    cancellation_reason_code: str | None = None
    cancellation_reason_addtl: tuple[str, ...] = ()


@dataclass(frozen=True)
class Camt029Resolution:
    """camt.029 RsltnOfInvstgtn — response to a camt.056."""

    assignment_id: str
    created_at: datetime
    assigner_routing: str
    assignee_routing: str
    status_confirmation: str
    orgnl_end_to_end_id: str
    orgnl_uetr: str
    cancellation_status_reason_code: str | None = None
    cancellation_status_reason_addtl: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pacs028StatusRequest:
    """pacs.028 FIToFIPmtStsReq — a status inquiry."""

    msg_id: str
    created_at: datetime
    orgnl_msg_id: str
    orgnl_msg_nm_id: str
    orgnl_end_to_end_id: str
    orgnl_uetr: str


@dataclass(frozen=True)
class Pain013Rfp:
    """pain.013 CdtrPmtActvtnReq — request for payment."""

    msg_id: str
    created_at: datetime
    initiating_party: str
    pmt_inf_id: str
    end_to_end_id: str
    amount_minor: int
    execution_date: date
    debtor_name: str
    debtor_agent: str
    creditor_name: str
    creditor_agent: str
    remittance: tuple[str, ...] = ()
    instr_for_cdtr_agt: str | None = None


@dataclass(frozen=True)
class Pain014RfpStatus:
    """pain.014 CdtrPmtActvtnReqStsRpt — RfP response."""

    msg_id: str
    created_at: datetime
    initiating_party: str
    orgnl_msg_id: str
    orgnl_msg_nm_id: str
    orgnl_pmt_inf_id: str
    orgnl_end_to_end_id: str
    tx_status: str
    status_reason_code: str | None = None
    status_reason_addtl: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pain001Initiation:
    """pain.001 CstmrCdtTrfInitn — customer/PSP initiation."""

    msg_id: str
    created_at: datetime
    initiating_party: str
    pmt_inf_id: str
    end_to_end_id: str
    amount_minor: int
    execution_date: date
    debtor_name: str
    debtor_account: str
    debtor_agent: str
    creditor_name: str
    creditor_account: str
    creditor_agent: str
    remittance: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pain002Status:
    """pain.002 CstmrPmtStsRpt — status to initiator."""

    msg_id: str
    created_at: datetime
    orgnl_msg_id: str
    orgnl_msg_nm_id: str
    orgnl_pmt_inf_id: str
    orgnl_end_to_end_id: str
    tx_status: str
    status_reason_code: str | None = None
    status_reason_addtl: tuple[str, ...] = ()


@dataclass(frozen=True)
class Entry:
    """A single statement/notification entry (camt.053/054/052)."""

    amount_minor: int
    credit_debit: str  # "CRDT" or "DBIT"
    status: str = "BOOK"
    additional_entry_info: str | None = None
    remittance: tuple[str, ...] = ()


@dataclass(frozen=True)
class Camt053Statement:
    """camt.053 BkToCstmrStmt — daily statement."""

    msg_id: str
    created_at: datetime
    statement_id: str
    account_id: str
    entries: tuple[Entry, ...] = ()


@dataclass(frozen=True)
class Camt054Notification:
    """camt.054 BkToCstmrDbtCdtNtfctn — credit/debit notification."""

    msg_id: str
    created_at: datetime
    notification_id: str
    account_id: str
    entries: tuple[Entry, ...] = ()


@dataclass(frozen=True)
class Camt052Report:
    """camt.052 BkToCstmrAcctRpt — intraday account report."""

    msg_id: str
    created_at: datetime
    report_id: str
    account_id: str
    entries: tuple[Entry, ...] = ()


@dataclass(frozen=True)
class Admi002Reject:
    """admi.002 MessageReject — technical reject."""

    related_ref: str
    rejecting_party_reason: str
    reason_description: str | None = None
    error_location: str | None = None
