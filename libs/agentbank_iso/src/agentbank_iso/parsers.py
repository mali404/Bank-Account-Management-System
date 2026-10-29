"""Parsers: ISO 20022 XML bytes → typed domain models.

Each ``parse_<msg>(xml) -> Model`` reverses the matching builder so that
``parse(build(model)) == model``. Parsing uses the shared xsdata parser; the
navigation below assumes documents produced by :mod:`agentbank_iso.builders`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from agentbank_common.money import parse_minor

from . import models
from ._serde import from_xml

if TYPE_CHECKING:
    from xsdata.models.datatype import XmlDate, XmlDateTime

__all__ = [
    "parse_admi002",
    "parse_camt029",
    "parse_camt052",
    "parse_camt053",
    "parse_camt054",
    "parse_camt056",
    "parse_envelope",
    "parse_head001",
    "parse_pacs002",
    "parse_pacs004",
    "parse_pacs008",
    "parse_pacs028",
    "parse_pain001",
    "parse_pain002",
    "parse_pain013",
    "parse_pain014",
]


def _dt(value: XmlDateTime) -> datetime:
    return value.to_datetime().astimezone(UTC).replace(microsecond=0)


def _date(value: XmlDate) -> date:
    return value.to_date()


def _minor(amount: object) -> int:
    return parse_minor(_decimal_str(amount.value))  # type: ignore[attr-defined]


def _decimal_str(value: Decimal) -> str:
    # money.parse_minor wants a plain two-place string; Decimal already holds it.
    return f"{value:.2f}"


def _routing(agent: object) -> str:
    return agent.fin_instn_id.clr_sys_mmb_id.mmb_id  # type: ignore[attr-defined,no-any-return]


def _account(acct: object) -> str:
    return acct.id.othr.id  # type: ignore[attr-defined,no-any-return]


def _first[T](items: list[T]) -> T | None:
    return items[0] if items else None


def parse_head001(xml: bytes) -> models.BusinessHeader:
    doc: Any = from_xml(xml, "head.001.001.02")
    return models.BusinessHeader(
        from_routing=_routing(doc.fr.fiid),
        to_routing=_routing(doc.to.fiid),
        biz_msg_idr=doc.biz_msg_idr,
        msg_def_idr=doc.msg_def_idr,
        created_at=_dt(doc.cre_dt),
        biz_svc=doc.biz_svc,
    )


def parse_pacs008(xml: bytes) -> models.Pacs008Payment:
    doc: Any = from_xml(xml, "pacs.008.001.08")
    body = doc.fito_ficstmr_cdt_trf
    grp = body.grp_hdr
    tx = body.cdt_trf_tx_inf[0]
    remittance: tuple[str, ...] = ()
    addtl: tuple[str, ...] = ()
    if tx.rmt_inf is not None:
        remittance = tuple(tx.rmt_inf.ustrd)
        strd = _first(tx.rmt_inf.strd)
        if strd is not None:
            addtl = tuple(strd.addtl_rmt_inf)
    instr = _first(tx.instr_for_cdtr_agt)
    return models.Pacs008Payment(
        msg_id=grp.msg_id,
        created_at=_dt(grp.cre_dt_tm),
        end_to_end_id=tx.pmt_id.end_to_end_id,
        uetr=tx.pmt_id.uetr,
        amount_minor=_minor(tx.intr_bk_sttlm_amt),
        settlement_date=_date(grp.intr_bk_sttlm_dt),
        debtor_name=tx.dbtr.nm,
        debtor_account=_account(tx.dbtr_acct),
        debtor_agent=_routing(tx.dbtr_agt),
        creditor_name=tx.cdtr.nm,
        creditor_account=_account(tx.cdtr_acct),
        creditor_agent=_routing(tx.cdtr_agt),
        remittance=remittance,
        ultimate_debtor_name=tx.ultmt_dbtr.nm if tx.ultmt_dbtr is not None else None,
        instr_for_cdtr_agt=instr.instr_inf if instr is not None else None,
        addtl_rmt_inf=addtl,
    )


def _status_reason(rsn_list: list[object]) -> tuple[str | None, tuple[str, ...]]:
    rsn = _first(rsn_list)
    if rsn is None:
        return None, ()
    code = rsn.rsn.cd if rsn.rsn is not None else None  # type: ignore[attr-defined]
    return code, tuple(rsn.addtl_inf)  # type: ignore[attr-defined]


def parse_pacs002(xml: bytes) -> models.Pacs002Status:
    doc: Any = from_xml(xml, "pacs.002.001.10")
    body = doc.fito_fipmt_sts_rpt
    tx = body.tx_inf_and_sts[0]
    code, addtl = _status_reason(tx.sts_rsn_inf)
    return models.Pacs002Status(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        orgnl_msg_id=tx.orgnl_grp_inf.orgnl_msg_id,
        orgnl_msg_nm_id=tx.orgnl_grp_inf.orgnl_msg_nm_id,
        orgnl_end_to_end_id=tx.orgnl_end_to_end_id,
        orgnl_uetr=tx.orgnl_uetr,
        tx_status=tx.tx_sts,
        status_reason_code=code,
        status_reason_addtl=addtl,
    )


def parse_pacs004(xml: bytes) -> models.Pacs004Return:
    doc: Any = from_xml(xml, "pacs.004.001.10")
    body = doc.pmt_rtr
    tx = body.tx_inf[0]
    code, addtl = _status_reason(tx.rtr_rsn_inf)
    return models.Pacs004Return(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        orgnl_msg_id=tx.orgnl_grp_inf.orgnl_msg_id,
        orgnl_msg_nm_id=tx.orgnl_grp_inf.orgnl_msg_nm_id,
        orgnl_end_to_end_id=tx.orgnl_end_to_end_id,
        orgnl_uetr=tx.orgnl_uetr,
        returned_amount_minor=_minor(tx.rtrd_intr_bk_sttlm_amt),
        settlement_date=_date(body.grp_hdr.intr_bk_sttlm_dt),
        return_reason_code=code,
        return_reason_addtl=addtl,
    )


def parse_camt056(xml: bytes) -> models.Camt056CancellationRequest:
    doc: Any = from_xml(xml, "camt.056.001.08")
    body = doc.fito_fipmt_cxl_req
    tx = body.undrlyg[0].tx_inf[0]
    rsn = _first(tx.cxl_rsn_inf)
    code = rsn.rsn.cd if rsn is not None and rsn.rsn is not None else None
    addtl = tuple(rsn.addtl_inf) if rsn is not None else ()
    return models.Camt056CancellationRequest(
        assignment_id=body.assgnmt.id,
        created_at=_dt(body.assgnmt.cre_dt_tm),
        assigner_routing=_routing(body.assgnmt.assgnr.agt),
        assignee_routing=_routing(body.assgnmt.assgne.agt),
        case_id=body.case.id,
        orgnl_msg_id=tx.orgnl_grp_inf.orgnl_msg_id,
        orgnl_msg_nm_id=tx.orgnl_grp_inf.orgnl_msg_nm_id,
        orgnl_end_to_end_id=tx.orgnl_end_to_end_id,
        orgnl_uetr=tx.orgnl_uetr,
        cancellation_reason_code=code,
        cancellation_reason_addtl=addtl,
    )


def parse_camt029(xml: bytes) -> models.Camt029Resolution:
    doc: Any = from_xml(xml, "camt.029.001.09")
    body = doc.rsltn_of_invstgtn
    tx = body.cxl_dtls[0].tx_inf_and_sts[0]
    rsn = _first(tx.cxl_sts_rsn_inf)
    code = rsn.rsn.cd if rsn is not None and rsn.rsn is not None else None
    addtl = tuple(rsn.addtl_inf) if rsn is not None else ()
    return models.Camt029Resolution(
        assignment_id=body.assgnmt.id,
        created_at=_dt(body.assgnmt.cre_dt_tm),
        assigner_routing=_routing(body.assgnmt.assgnr.agt),
        assignee_routing=_routing(body.assgnmt.assgne.agt),
        status_confirmation=body.sts.conf,
        orgnl_end_to_end_id=tx.orgnl_end_to_end_id,
        orgnl_uetr=tx.orgnl_uetr,
        cancellation_status_reason_code=code,
        cancellation_status_reason_addtl=addtl,
    )


def parse_pacs028(xml: bytes) -> models.Pacs028StatusRequest:
    doc: Any = from_xml(xml, "pacs.028.001.03")
    body = doc.fito_fipmt_sts_req
    tx = body.tx_inf[0]
    return models.Pacs028StatusRequest(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        orgnl_msg_id=tx.orgnl_grp_inf.orgnl_msg_id,
        orgnl_msg_nm_id=tx.orgnl_grp_inf.orgnl_msg_nm_id,
        orgnl_end_to_end_id=tx.orgnl_end_to_end_id,
        orgnl_uetr=tx.orgnl_uetr,
    )


def parse_pain013(xml: bytes) -> models.Pain013Rfp:
    doc: Any = from_xml(xml, "pain.013.001.07")
    body = doc.cdtr_pmt_actvtn_req
    pmt = body.pmt_inf[0]
    tx = pmt.cdt_trf_tx[0]
    instr = _first(tx.instr_for_cdtr_agt)
    remittance = tuple(tx.rmt_inf.ustrd) if tx.rmt_inf is not None else ()
    return models.Pain013Rfp(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        initiating_party=body.grp_hdr.initg_pty.nm,
        pmt_inf_id=pmt.pmt_inf_id,
        end_to_end_id=tx.pmt_id.end_to_end_id,
        amount_minor=_minor(tx.amt.instd_amt),
        execution_date=_date(pmt.reqd_exctn_dt.dt),
        debtor_name=pmt.dbtr.nm,
        debtor_agent=_routing(pmt.dbtr_agt),
        creditor_name=tx.cdtr.nm,
        creditor_agent=_routing(tx.cdtr_agt),
        remittance=remittance,
        instr_for_cdtr_agt=instr.instr_inf if instr is not None else None,
    )


def parse_pain014(xml: bytes) -> models.Pain014RfpStatus:
    doc: Any = from_xml(xml, "pain.014.001.07")
    body = doc.cdtr_pmt_actvtn_req_sts_rpt
    pmt = body.orgnl_pmt_inf_and_sts[0]
    tx = pmt.tx_inf_and_sts[0]
    code, addtl = _status_reason(tx.sts_rsn_inf)
    return models.Pain014RfpStatus(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        initiating_party=body.grp_hdr.initg_pty.nm,
        orgnl_msg_id=body.orgnl_grp_inf_and_sts.orgnl_msg_id,
        orgnl_msg_nm_id=body.orgnl_grp_inf_and_sts.orgnl_msg_nm_id,
        orgnl_pmt_inf_id=pmt.orgnl_pmt_inf_id,
        orgnl_end_to_end_id=tx.orgnl_end_to_end_id,
        tx_status=tx.tx_sts,
        status_reason_code=code,
        status_reason_addtl=addtl,
    )


def parse_pain001(xml: bytes) -> models.Pain001Initiation:
    doc: Any = from_xml(xml, "pain.001.001.09")
    body = doc.cstmr_cdt_trf_initn
    pmt = body.pmt_inf[0]
    tx = pmt.cdt_trf_tx_inf[0]
    remittance = tuple(tx.rmt_inf.ustrd) if tx.rmt_inf is not None else ()
    return models.Pain001Initiation(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        initiating_party=body.grp_hdr.initg_pty.nm,
        pmt_inf_id=pmt.pmt_inf_id,
        end_to_end_id=tx.pmt_id.end_to_end_id,
        amount_minor=_minor(tx.amt.instd_amt),
        execution_date=_date(pmt.reqd_exctn_dt.dt),
        debtor_name=pmt.dbtr.nm,
        debtor_account=_account(pmt.dbtr_acct),
        debtor_agent=_routing(pmt.dbtr_agt),
        creditor_name=tx.cdtr.nm,
        creditor_account=_account(tx.cdtr_acct),
        creditor_agent=_routing(tx.cdtr_agt),
        remittance=remittance,
    )


def parse_pain002(xml: bytes) -> models.Pain002Status:
    doc: Any = from_xml(xml, "pain.002.001.10")
    body = doc.cstmr_pmt_sts_rpt
    pmt = body.orgnl_pmt_inf_and_sts[0]
    tx = pmt.tx_inf_and_sts[0]
    code, addtl = _status_reason(tx.sts_rsn_inf)
    return models.Pain002Status(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        orgnl_msg_id=body.orgnl_grp_inf_and_sts.orgnl_msg_id,
        orgnl_msg_nm_id=body.orgnl_grp_inf_and_sts.orgnl_msg_nm_id,
        orgnl_pmt_inf_id=pmt.orgnl_pmt_inf_id,
        orgnl_end_to_end_id=tx.orgnl_end_to_end_id,
        tx_status=tx.tx_sts,
        status_reason_code=code,
        status_reason_addtl=addtl,
    )


def _parse_entry(ntry: object) -> models.Entry:
    remittance: tuple[str, ...] = ()
    dtls = _first(ntry.ntry_dtls)  # type: ignore[attr-defined]
    if dtls is not None:
        txd = _first(dtls.tx_dtls)
        if txd is not None and txd.rmt_inf is not None:
            remittance = tuple(txd.rmt_inf.ustrd)
    return models.Entry(
        amount_minor=_minor(ntry.amt),  # type: ignore[attr-defined]
        credit_debit=ntry.cdt_dbt_ind.value,  # type: ignore[attr-defined]
        status=ntry.sts.cd,  # type: ignore[attr-defined]
        additional_entry_info=ntry.addtl_ntry_inf,  # type: ignore[attr-defined]
        remittance=remittance,
    )


def parse_camt053(xml: bytes) -> models.Camt053Statement:
    doc: Any = from_xml(xml, "camt.053.001.08")
    body = doc.bk_to_cstmr_stmt
    stmt = body.stmt[0]
    return models.Camt053Statement(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        statement_id=stmt.id,
        account_id=_account(stmt.acct),
        entries=tuple(_parse_entry(e) for e in stmt.ntry),
    )


def parse_camt054(xml: bytes) -> models.Camt054Notification:
    doc: Any = from_xml(xml, "camt.054.001.08")
    body = doc.bk_to_cstmr_dbt_cdt_ntfctn
    ntf = body.ntfctn[0]
    return models.Camt054Notification(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        notification_id=ntf.id,
        account_id=_account(ntf.acct),
        entries=tuple(_parse_entry(e) for e in ntf.ntry),
    )


def parse_camt052(xml: bytes) -> models.Camt052Report:
    doc: Any = from_xml(xml, "camt.052.001.08")
    body = doc.bk_to_cstmr_acct_rpt
    rpt = body.rpt[0]
    return models.Camt052Report(
        msg_id=body.grp_hdr.msg_id,
        created_at=_dt(body.grp_hdr.cre_dt_tm),
        report_id=rpt.id,
        account_id=_account(rpt.acct),
        entries=tuple(_parse_entry(e) for e in rpt.ntry),
    )


def parse_admi002(xml: bytes) -> models.Admi002Reject:
    doc: Any = from_xml(xml, "admi.002.001.01")
    body = doc.admi_002_001_01
    return models.Admi002Reject(
        related_ref=body.rltd_ref.ref,
        rejecting_party_reason=body.rsn.rjctg_pty_rsn,
        reason_description=body.rsn.rsn_desc,
        error_location=body.rsn.err_lctn,
    )


def parse_envelope(xml: bytes) -> tuple[models.BusinessHeader, bytes]:
    """Split an envelope and parse its header; return ``(header, document_xml)``."""
    from ._envelope import parse_envelope as _split

    header_xml, document_xml = _split(xml)
    return parse_head001(header_xml), document_xml
