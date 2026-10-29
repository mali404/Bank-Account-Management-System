"""Builders: typed domain models → XSD-valid ISO 20022 XML bytes.

Every SPEC §6.1 message has a ``build_<msg>(model) -> bytes`` function plus the
generic :func:`to_xml`. Amounts come from :mod:`agentbank_common.money` (integer
minor units serialised as a two-place decimal, ``Ccy="USD"``); identifiers from
:mod:`agentbank_common.ids`. Builders reject free-text values that exceed the
XSD ``maxLength`` for their element with :class:`FieldLengthError`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from xsdata.models.datatype import XmlDate, XmlDateTime

from agentbank_common.money import CURRENCY, format_minor
from agentbank_common.timeutil import format_iso8601

from . import models
from ._serde import serialize, to_xml
from .errors import FieldLengthError
from .gen import admi002_001_01 as g_admi002
from .gen import camt029_001_09 as g_camt029
from .gen import camt052_001_08 as g_camt052
from .gen import camt053_001_08 as g_camt053
from .gen import camt054_001_08 as g_camt054
from .gen import camt056_001_08 as g_camt056
from .gen import head001_001_02 as g_head001
from .gen import pacs002_001_10 as g_pacs002
from .gen import pacs004_001_10 as g_pacs004
from .gen import pacs008_001_08 as g_pacs008
from .gen import pacs028_001_03 as g_pacs028
from .gen import pain001_001_09 as g_pain001
from .gen import pain002_001_10 as g_pain002
from .gen import pain013_001_07 as g_pain013
from .gen import pain014_001_07 as g_pain014
from .messages import get_spec

if TYPE_CHECKING:
    from types import ModuleType

__all__ = [
    "build_admi002",
    "build_camt029",
    "build_camt052",
    "build_camt053",
    "build_camt054",
    "build_camt056",
    "build_head001",
    "build_pacs002",
    "build_pacs004",
    "build_pacs008",
    "build_pacs028",
    "build_pain001",
    "build_pain002",
    "build_pain013",
    "build_pain014",
    "envelope",
    "to_xml",
]

# Free-text length limits (XSD maxLength) per element label; see README table.
_NAME_MAX = 140
_USTRD_MAX = 140
_INSTR_MAX = 140
_ADDTL_INFO_MAX = 105
_NTRY_INFO_MAX = 500
_RSN_DESC_MAX = 350


def _text(value: str, max_length: int, label: str) -> str:
    if len(value) > max_length:
        raise FieldLengthError(label, max_length, len(value))
    return value


def _texts(values: tuple[str, ...], max_length: int, label: str) -> list[str]:
    return [_text(v, max_length, label) for v in values]


def _dt(moment: datetime) -> XmlDateTime:
    return XmlDateTime.from_string(format_iso8601(moment.replace(microsecond=0)))


def _date(day: date) -> XmlDate:
    return XmlDate.from_date(day)


def _amount(amount_cls: type, minor: int) -> Any:
    return amount_cls(value=Decimal(format_minor(minor)), ccy=CURRENCY)


def _agent(m: ModuleType, routing: str) -> Any:
    return m.BranchAndFinancialInstitutionIdentification6(
        fin_instn_id=m.FinancialInstitutionIdentification18(
            clr_sys_mmb_id=m.ClearingSystemMemberIdentification2(
                clr_sys_id=m.ClearingSystemIdentification2Choice(cd="USABA"),
                mmb_id=routing,
            )
        )
    )


def _account(m: ModuleType, number: str) -> Any:
    return m.CashAccount38(
        id=m.AccountIdentification4Choice(othr=m.GenericAccountIdentification1(id=number))
    )


def _party(m: ModuleType, name: str) -> Any:
    return m.PartyIdentification135(nm=_text(name, _NAME_MAX, "Nm"))


def _render(document: object, message_id: str) -> bytes:
    return serialize(document, get_spec(message_id).namespace)


# --------------------------------------------------------------------------- #
# head.001 BAH + envelope
# --------------------------------------------------------------------------- #
def build_head001(header: models.BusinessHeader) -> bytes:
    m = g_head001
    doc = m.AppHdr(
        fr=m.Party44Choice(fiid=_agent(m, header.from_routing)),
        to=m.Party44Choice(fiid=_agent(m, header.to_routing)),
        biz_msg_idr=header.biz_msg_idr,
        msg_def_idr=header.msg_def_idr,
        biz_svc=header.biz_svc,
        cre_dt=_dt(header.created_at),
    )
    return _render(doc, "head.001.001.02")


def envelope(header: models.BusinessHeader, document: bytes) -> bytes:
    """Wrap a serialised document in a BAH envelope for switch traffic.

    Produces ``<Envelope><AppHdr/><Document/></Envelope>`` in a neutral testbed
    namespace. The two children keep their own ISO namespaces, so each half can
    be validated independently with :func:`parse_envelope`.
    """
    from ._envelope import wrap_envelope

    return wrap_envelope(build_head001(header), document)


# --------------------------------------------------------------------------- #
# pacs.008 credit transfer
# --------------------------------------------------------------------------- #
def build_pacs008(payment: models.Pacs008Payment) -> bytes:
    m = g_pacs008
    rmt = None
    if payment.remittance or payment.addtl_rmt_inf:
        strd = []
        if payment.addtl_rmt_inf:
            strd = [
                m.StructuredRemittanceInformation16(
                    addtl_rmt_inf=_texts(payment.addtl_rmt_inf, _USTRD_MAX, "AddtlRmtInf")
                )
            ]
        rmt = m.RemittanceInformation16(
            ustrd=_texts(payment.remittance, _USTRD_MAX, "Ustrd"),
            strd=strd,
        )
    instr = None
    if payment.instr_for_cdtr_agt is not None:
        instr = [
            m.InstructionForCreditorAgent1(
                instr_inf=_text(payment.instr_for_cdtr_agt, _INSTR_MAX, "InstrInf")
            )
        ]
    ultmt_dbtr = None
    if payment.ultimate_debtor_name is not None:
        ultmt_dbtr = _party(m, payment.ultimate_debtor_name)

    tx = m.CreditTransferTransaction39(
        pmt_id=m.PaymentIdentification7(end_to_end_id=payment.end_to_end_id, uetr=payment.uetr),
        intr_bk_sttlm_amt=_amount(m.ActiveCurrencyAndAmount, payment.amount_minor),
        chrg_br=m.ChargeBearerType1Code.SLEV,
        ultmt_dbtr=ultmt_dbtr,
        dbtr=_party(m, payment.debtor_name),
        dbtr_acct=_account(m, payment.debtor_account),
        dbtr_agt=_agent(m, payment.debtor_agent),
        cdtr_agt=_agent(m, payment.creditor_agent),
        cdtr=_party(m, payment.creditor_name),
        cdtr_acct=_account(m, payment.creditor_account),
        instr_for_cdtr_agt=instr or [],
        rmt_inf=rmt,
    )
    doc = m.Document(
        fito_ficstmr_cdt_trf=m.FitoFicustomerCreditTransferV08(
            grp_hdr=m.GroupHeader93(
                msg_id=payment.msg_id,
                cre_dt_tm=_dt(payment.created_at),
                nb_of_txs="1",
                sttlm_inf=m.SettlementInstruction7(sttlm_mtd=m.SettlementMethod1Code.CLRG),
                intr_bk_sttlm_dt=_date(payment.settlement_date),
            ),
            cdt_trf_tx_inf=[tx],
        )
    )
    return _render(doc, "pacs.008.001.08")


# --------------------------------------------------------------------------- #
# pacs.002 payment status report
# --------------------------------------------------------------------------- #
def build_pacs002(status: models.Pacs002Status) -> bytes:
    m = g_pacs002
    rsn = None
    if status.status_reason_code is not None or status.status_reason_addtl:
        rsn = [
            m.StatusReasonInformation12(
                rsn=(
                    m.StatusReason6Choice(cd=status.status_reason_code)
                    if status.status_reason_code is not None
                    else None
                ),
                addtl_inf=_texts(status.status_reason_addtl, _ADDTL_INFO_MAX, "AddtlInf"),
            )
        ]
    tx = m.PaymentTransaction110(
        orgnl_grp_inf=m.OriginalGroupInformation29(
            orgnl_msg_id=status.orgnl_msg_id, orgnl_msg_nm_id=status.orgnl_msg_nm_id
        ),
        orgnl_end_to_end_id=status.orgnl_end_to_end_id,
        orgnl_uetr=status.orgnl_uetr,
        tx_sts=status.tx_status,
        sts_rsn_inf=rsn or [],
    )
    doc = m.Document(
        fito_fipmt_sts_rpt=m.FitoFipaymentStatusReportV10(
            grp_hdr=m.GroupHeader91(msg_id=status.msg_id, cre_dt_tm=_dt(status.created_at)),
            tx_inf_and_sts=[tx],
        )
    )
    return _render(doc, "pacs.002.001.10")


# --------------------------------------------------------------------------- #
# pacs.004 payment return
# --------------------------------------------------------------------------- #
def build_pacs004(ret: models.Pacs004Return) -> bytes:
    m = g_pacs004
    rsn = None
    if ret.return_reason_code is not None or ret.return_reason_addtl:
        rsn = [
            m.PaymentReturnReason6(
                rsn=(
                    m.ReturnReason5Choice(cd=ret.return_reason_code)
                    if ret.return_reason_code is not None
                    else None
                ),
                addtl_inf=_texts(ret.return_reason_addtl, _ADDTL_INFO_MAX, "AddtlInf"),
            )
        ]
    tx = m.PaymentTransaction118(
        orgnl_grp_inf=m.OriginalGroupInformation29(
            orgnl_msg_id=ret.orgnl_msg_id, orgnl_msg_nm_id=ret.orgnl_msg_nm_id
        ),
        orgnl_end_to_end_id=ret.orgnl_end_to_end_id,
        orgnl_uetr=ret.orgnl_uetr,
        rtrd_intr_bk_sttlm_amt=_amount(m.ActiveCurrencyAndAmount, ret.returned_amount_minor),
        rtr_rsn_inf=rsn or [],
    )
    doc = m.Document(
        pmt_rtr=m.PaymentReturnV10(
            grp_hdr=m.GroupHeader90(
                msg_id=ret.msg_id,
                cre_dt_tm=_dt(ret.created_at),
                nb_of_txs="1",
                intr_bk_sttlm_dt=_date(ret.settlement_date),
                sttlm_inf=m.SettlementInstruction7(sttlm_mtd=m.SettlementMethod1Code.CLRG),
            ),
            tx_inf=[tx],
        )
    )
    return _render(doc, "pacs.004.001.10")


# --------------------------------------------------------------------------- #
# camt.056 cancellation request
# --------------------------------------------------------------------------- #
def build_camt056(req: models.Camt056CancellationRequest) -> bytes:
    m = g_camt056
    rsn = None
    if req.cancellation_reason_code is not None or req.cancellation_reason_addtl:
        rsn = [
            m.PaymentCancellationReason5(
                rsn=(
                    m.CancellationReason33Choice(cd=req.cancellation_reason_code)
                    if req.cancellation_reason_code is not None
                    else None
                ),
                addtl_inf=_texts(req.cancellation_reason_addtl, _ADDTL_INFO_MAX, "AddtlInf"),
            )
        ]
    tx = m.PaymentTransaction106(
        orgnl_grp_inf=m.OriginalGroupInformation29(
            orgnl_msg_id=req.orgnl_msg_id, orgnl_msg_nm_id=req.orgnl_msg_nm_id
        ),
        orgnl_end_to_end_id=req.orgnl_end_to_end_id,
        orgnl_uetr=req.orgnl_uetr,
        cxl_rsn_inf=rsn or [],
    )
    doc = m.Document(
        fito_fipmt_cxl_req=m.FitoFipaymentCancellationRequestV08(
            assgnmt=m.CaseAssignment5(
                id=req.assignment_id,
                assgnr=m.Party40Choice(agt=_agent(m, req.assigner_routing)),
                assgne=m.Party40Choice(agt=_agent(m, req.assignee_routing)),
                cre_dt_tm=_dt(req.created_at),
            ),
            case=m.Case5(
                id=req.case_id,
                cretr=m.Party40Choice(agt=_agent(m, req.assigner_routing)),
            ),
            undrlyg=[m.UnderlyingTransaction23(tx_inf=[tx])],
        )
    )
    return _render(doc, "camt.056.001.08")


# --------------------------------------------------------------------------- #
# camt.029 resolution of investigation
# --------------------------------------------------------------------------- #
def build_camt029(res: models.Camt029Resolution) -> bytes:
    m = g_camt029
    rsn = None
    if res.cancellation_status_reason_code is not None or res.cancellation_status_reason_addtl:
        rsn = [
            m.CancellationStatusReason4(
                rsn=(
                    m.CancellationStatusReason3Choice(cd=res.cancellation_status_reason_code)
                    if res.cancellation_status_reason_code is not None
                    else None
                ),
                addtl_inf=_texts(res.cancellation_status_reason_addtl, _ADDTL_INFO_MAX, "AddtlInf"),
            )
        ]
    tx = m.PaymentTransaction102(
        orgnl_end_to_end_id=res.orgnl_end_to_end_id,
        orgnl_uetr=res.orgnl_uetr,
        cxl_sts_rsn_inf=rsn or [],
    )
    doc = m.Document(
        rsltn_of_invstgtn=m.ResolutionOfInvestigationV09(
            assgnmt=m.CaseAssignment5(
                id=res.assignment_id,
                assgnr=m.Party40Choice(agt=_agent(m, res.assigner_routing)),
                assgne=m.Party40Choice(agt=_agent(m, res.assignee_routing)),
                cre_dt_tm=_dt(res.created_at),
            ),
            sts=m.InvestigationStatus5Choice(conf=res.status_confirmation),
            cxl_dtls=[m.UnderlyingTransaction22(tx_inf_and_sts=[tx])],
        )
    )
    return _render(doc, "camt.029.001.09")


# --------------------------------------------------------------------------- #
# pacs.028 status request
# --------------------------------------------------------------------------- #
def build_pacs028(req: models.Pacs028StatusRequest) -> bytes:
    m = g_pacs028
    tx = m.PaymentTransaction113(
        orgnl_grp_inf=m.OriginalGroupInformation29(
            orgnl_msg_id=req.orgnl_msg_id, orgnl_msg_nm_id=req.orgnl_msg_nm_id
        ),
        orgnl_end_to_end_id=req.orgnl_end_to_end_id,
        orgnl_uetr=req.orgnl_uetr,
    )
    doc = m.Document(
        fito_fipmt_sts_req=m.FitoFipaymentStatusRequestV03(
            grp_hdr=m.GroupHeader91(msg_id=req.msg_id, cre_dt_tm=_dt(req.created_at)),
            tx_inf=[tx],
        )
    )
    return _render(doc, "pacs.028.001.03")


# --------------------------------------------------------------------------- #
# pain.013 request for payment
# --------------------------------------------------------------------------- #
def build_pain013(rfp: models.Pain013Rfp) -> bytes:
    m = g_pain013
    rmt = (
        m.RemittanceInformation16(ustrd=_texts(rfp.remittance, _USTRD_MAX, "Ustrd"))
        if rfp.remittance
        else None
    )
    instr = None
    if rfp.instr_for_cdtr_agt is not None:
        instr = [
            m.InstructionForCreditorAgent1(
                instr_inf=_text(rfp.instr_for_cdtr_agt, _INSTR_MAX, "InstrInf")
            )
        ]
    cdt_trf = m.CreditTransferTransaction35(
        pmt_id=m.PaymentIdentification6(end_to_end_id=rfp.end_to_end_id),
        amt=m.AmountType4Choice(
            instd_amt=_amount(m.ActiveOrHistoricCurrencyAndAmount, rfp.amount_minor)
        ),
        chrg_br=m.ChargeBearerType1Code.SLEV,
        cdtr_agt=_agent(m, rfp.creditor_agent),
        cdtr=_party(m, rfp.creditor_name),
        instr_for_cdtr_agt=instr or [],
        rmt_inf=rmt,
    )
    pmt_inf = m.PaymentInstruction31(
        pmt_inf_id=rfp.pmt_inf_id,
        pmt_mtd=m.PaymentMethod7Code.TRF,
        reqd_exctn_dt=m.DateAndDateTime2Choice(dt=_date(rfp.execution_date)),
        dbtr=_party(m, rfp.debtor_name),
        dbtr_agt=_agent(m, rfp.debtor_agent),
        cdt_trf_tx=[cdt_trf],
    )
    doc = m.Document(
        cdtr_pmt_actvtn_req=m.CreditorPaymentActivationRequestV07(
            grp_hdr=m.GroupHeader78(
                msg_id=rfp.msg_id,
                cre_dt_tm=_dt(rfp.created_at),
                nb_of_txs="1",
                initg_pty=_party(m, rfp.initiating_party),
            ),
            pmt_inf=[pmt_inf],
        )
    )
    return _render(doc, "pain.013.001.07")


# --------------------------------------------------------------------------- #
# pain.014 request-for-payment status
# --------------------------------------------------------------------------- #
def build_pain014(status: models.Pain014RfpStatus) -> bytes:
    m = g_pain014
    rsn = None
    if status.status_reason_code is not None or status.status_reason_addtl:
        rsn = [
            m.StatusReasonInformation12(
                rsn=(
                    m.StatusReason6Choice(cd=status.status_reason_code)
                    if status.status_reason_code is not None
                    else None
                ),
                addtl_inf=_texts(status.status_reason_addtl, _ADDTL_INFO_MAX, "AddtlInf"),
            )
        ]
    tx = m.PaymentTransaction104(
        orgnl_end_to_end_id=status.orgnl_end_to_end_id,
        tx_sts=status.tx_status,
        sts_rsn_inf=rsn or [],
    )
    pmt_sts = m.OriginalPaymentInstruction31(
        orgnl_pmt_inf_id=status.orgnl_pmt_inf_id,
        tx_inf_and_sts=[tx],
    )
    doc = m.Document(
        cdtr_pmt_actvtn_req_sts_rpt=m.CreditorPaymentActivationRequestStatusReportV07(
            grp_hdr=m.GroupHeader87(
                msg_id=status.msg_id,
                cre_dt_tm=_dt(status.created_at),
                initg_pty=_party(m, status.initiating_party),
            ),
            orgnl_grp_inf_and_sts=m.OriginalGroupInformation30(
                orgnl_msg_id=status.orgnl_msg_id, orgnl_msg_nm_id=status.orgnl_msg_nm_id
            ),
            orgnl_pmt_inf_and_sts=[pmt_sts],
        )
    )
    return _render(doc, "pain.014.001.07")


# --------------------------------------------------------------------------- #
# pain.001 customer credit transfer initiation
# --------------------------------------------------------------------------- #
def build_pain001(init: models.Pain001Initiation) -> bytes:
    m = g_pain001
    rmt = (
        m.RemittanceInformation16(ustrd=_texts(init.remittance, _USTRD_MAX, "Ustrd"))
        if init.remittance
        else None
    )
    tx = m.CreditTransferTransaction34(
        pmt_id=m.PaymentIdentification6(end_to_end_id=init.end_to_end_id),
        amt=m.AmountType4Choice(
            instd_amt=_amount(m.ActiveOrHistoricCurrencyAndAmount, init.amount_minor)
        ),
        cdtr_agt=_agent(m, init.creditor_agent),
        cdtr=_party(m, init.creditor_name),
        cdtr_acct=_account(m, init.creditor_account),
        rmt_inf=rmt,
    )
    pmt_inf = m.PaymentInstruction30(
        pmt_inf_id=init.pmt_inf_id,
        pmt_mtd=m.PaymentMethod3Code.TRF,
        reqd_exctn_dt=m.DateAndDateTime2Choice(dt=_date(init.execution_date)),
        dbtr=_party(m, init.debtor_name),
        dbtr_acct=_account(m, init.debtor_account),
        dbtr_agt=_agent(m, init.debtor_agent),
        chrg_br=m.ChargeBearerType1Code.SLEV,
        cdt_trf_tx_inf=[tx],
    )
    doc = m.Document(
        cstmr_cdt_trf_initn=m.CustomerCreditTransferInitiationV09(
            grp_hdr=m.GroupHeader85(
                msg_id=init.msg_id,
                cre_dt_tm=_dt(init.created_at),
                nb_of_txs="1",
                initg_pty=_party(m, init.initiating_party),
            ),
            pmt_inf=[pmt_inf],
        )
    )
    return _render(doc, "pain.001.001.09")


# --------------------------------------------------------------------------- #
# pain.002 customer payment status report
# --------------------------------------------------------------------------- #
def build_pain002(status: models.Pain002Status) -> bytes:
    m = g_pain002
    rsn = None
    if status.status_reason_code is not None or status.status_reason_addtl:
        rsn = [
            m.StatusReasonInformation12(
                rsn=(
                    m.StatusReason6Choice(cd=status.status_reason_code)
                    if status.status_reason_code is not None
                    else None
                ),
                addtl_inf=_texts(status.status_reason_addtl, _ADDTL_INFO_MAX, "AddtlInf"),
            )
        ]
    tx = m.PaymentTransaction105(
        orgnl_end_to_end_id=status.orgnl_end_to_end_id,
        tx_sts=status.tx_status,
        sts_rsn_inf=rsn or [],
    )
    pmt_sts = m.OriginalPaymentInstruction32(
        orgnl_pmt_inf_id=status.orgnl_pmt_inf_id,
        tx_inf_and_sts=[tx],
    )
    doc = m.Document(
        cstmr_pmt_sts_rpt=m.CustomerPaymentStatusReportV10(
            grp_hdr=m.GroupHeader86(msg_id=status.msg_id, cre_dt_tm=_dt(status.created_at)),
            orgnl_grp_inf_and_sts=m.OriginalGroupHeader17(
                orgnl_msg_id=status.orgnl_msg_id, orgnl_msg_nm_id=status.orgnl_msg_nm_id
            ),
            orgnl_pmt_inf_and_sts=[pmt_sts],
        )
    )
    return _render(doc, "pain.002.001.10")


# --------------------------------------------------------------------------- #
# camt statement / notification / report entries
# --------------------------------------------------------------------------- #
def _report_entry(m: ModuleType, entry: models.Entry) -> Any:
    ntry_dtls = []
    if entry.remittance:
        ntry_dtls = [
            m.EntryDetails9(
                tx_dtls=[
                    m.EntryTransaction10(
                        rmt_inf=m.RemittanceInformation16(
                            ustrd=_texts(entry.remittance, _USTRD_MAX, "Ustrd")
                        )
                    )
                ]
            )
        ]
    addtl = (
        _text(entry.additional_entry_info, _NTRY_INFO_MAX, "AddtlNtryInf")
        if entry.additional_entry_info is not None
        else None
    )
    return m.ReportEntry10(
        amt=_amount(m.ActiveOrHistoricCurrencyAndAmount, entry.amount_minor),
        cdt_dbt_ind=m.CreditDebitCode(entry.credit_debit),
        sts=m.EntryStatus1Choice(cd=entry.status),
        bk_tx_cd=m.BankTransactionCodeStructure4(
            prtry=m.ProprietaryBankTransactionCodeStructure1(cd="NTRF", issr="SimNow")
        ),
        ntry_dtls=ntry_dtls,
        addtl_ntry_inf=addtl,
    )


def _closing_balance(m: ModuleType, entries: tuple[models.Entry, ...], day: datetime) -> Any:
    """A single mandatory CLBD balance synthesised from the entry net amount."""
    net = sum(e.amount_minor if e.credit_debit == "CRDT" else -e.amount_minor for e in entries)
    return m.CashBalance8(
        tp=m.BalanceType13(cd_or_prtry=m.BalanceType10Choice(cd="CLBD")),
        amt=_amount(m.ActiveOrHistoricCurrencyAndAmount, abs(net)),
        cdt_dbt_ind=m.CreditDebitCode("CRDT" if net >= 0 else "DBIT"),
        dt=m.DateAndDateTime2Choice(dt=_date(day.date())),
    )


def build_camt053(stmt: models.Camt053Statement) -> bytes:
    m = g_camt053
    doc = m.Document(
        bk_to_cstmr_stmt=m.BankToCustomerStatementV08(
            grp_hdr=m.GroupHeader81(msg_id=stmt.msg_id, cre_dt_tm=_dt(stmt.created_at)),
            stmt=[
                m.AccountStatement9(
                    id=stmt.statement_id,
                    acct=m.CashAccount39(
                        id=m.AccountIdentification4Choice(
                            othr=m.GenericAccountIdentification1(id=stmt.account_id)
                        )
                    ),
                    bal=[_closing_balance(m, stmt.entries, stmt.created_at)],
                    ntry=[_report_entry(m, e) for e in stmt.entries],
                )
            ],
        )
    )
    return _render(doc, "camt.053.001.08")


def build_camt054(ntfctn: models.Camt054Notification) -> bytes:
    m = g_camt054
    doc = m.Document(
        bk_to_cstmr_dbt_cdt_ntfctn=m.BankToCustomerDebitCreditNotificationV08(
            grp_hdr=m.GroupHeader81(msg_id=ntfctn.msg_id, cre_dt_tm=_dt(ntfctn.created_at)),
            ntfctn=[
                m.AccountNotification17(
                    id=ntfctn.notification_id,
                    acct=m.CashAccount39(
                        id=m.AccountIdentification4Choice(
                            othr=m.GenericAccountIdentification1(id=ntfctn.account_id)
                        )
                    ),
                    ntry=[_report_entry(m, e) for e in ntfctn.entries],
                )
            ],
        )
    )
    return _render(doc, "camt.054.001.08")


def build_camt052(rpt: models.Camt052Report) -> bytes:
    m = g_camt052
    doc = m.Document(
        bk_to_cstmr_acct_rpt=m.BankToCustomerAccountReportV08(
            grp_hdr=m.GroupHeader81(msg_id=rpt.msg_id, cre_dt_tm=_dt(rpt.created_at)),
            rpt=[
                m.AccountReport25(
                    id=rpt.report_id,
                    acct=m.CashAccount39(
                        id=m.AccountIdentification4Choice(
                            othr=m.GenericAccountIdentification1(id=rpt.account_id)
                        )
                    ),
                    ntry=[_report_entry(m, e) for e in rpt.entries],
                )
            ],
        )
    )
    return _render(doc, "camt.052.001.08")


# --------------------------------------------------------------------------- #
# admi.002 message reject
# --------------------------------------------------------------------------- #
def build_admi002(reject: models.Admi002Reject) -> bytes:
    m = g_admi002
    doc = m.Document(
        admi_002_001_01=m.Admi00200101(
            rltd_ref=m.MessageReference(ref=reject.related_ref),
            rsn=m.RejectionReason2(
                rjctg_pty_rsn=reject.rejecting_party_reason,
                err_lctn=reject.error_location,
                rsn_desc=(
                    _text(reject.reason_description, _RSN_DESC_MAX, "RsnDesc")
                    if reject.reason_description is not None
                    else None
                ),
            ),
        )
    )
    return _render(doc, "admi.002.001.01")
