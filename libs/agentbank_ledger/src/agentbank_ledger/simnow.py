"""SimNow switch pipeline (SPEC §5.3).

Inbound order: archive, XSD validation, usage rules, duplicate detection
(MsgId, EndToEndId, UETR), participant and network limits, a TigerBeetle-style
pending transfer, forward to the creditor, then post on ACSC or void on RJCT
or receiver timeout. Every archived blob is linked by
``h_i = SHA256(h_{i-1} || c14n(xml_i))`` with ``h_0`` 32 zero bytes.

The receiver timeout is ``RECEIVER_TIMEOUT_S`` (default 20). The in-process
participant adapter compares that deadline with the creditor's declared
response delay, which is how a NATS request timeout is decided without
sleeping the test suite. A delay above the deadline is ``RJCT`` / ``AB05``
and voids the pending transfer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

import lxml.etree as ET

from agentbank_iso import builders, models, parsers
from agentbank_iso.usage_rules import UsageRuleValidator
from agentbank_iso.validate import validate_xsd

from .errors import SettlementError
from .settlement import SettlementLedger

__all__ = ["ArchivedMessage", "Participant", "ReturnDecision", "SimNow", "SwitchReply"]

_ZERO = b"\x00" * 32


def c14n(xml: bytes) -> bytes:
    """Exclusive canonical form, or the raw bytes when ``xml`` is not well-formed."""
    try:
        root = ET.fromstring(xml)
    except ET.XMLSyntaxError:
        return xml
    rendered = ET.tostring(root, method="c14n", exclusive=True)
    return bytes(rendered)


@dataclass
class ArchivedMessage:
    """One link in the switch hash chain."""

    hash: bytes
    xml: bytes
    message_id: str
    sender: str


@dataclass(frozen=True)
class SwitchReply:
    """Result of submitting one message to the switch."""

    tx_status: str
    reason_code: str | None
    pacs002_xml: bytes
    elapsed_s: float
    detail: str = ""


@dataclass
class ReturnDecision:
    """Creditor answer to a camt.056. ``deferred`` parks it for an ops decision."""

    accept: bool
    deferred: bool = False
    pacs004_xml: bytes | None = None
    camt029_xml: bytes | None = None


@dataclass
class StoredPayment:
    """A pacs.008 the switch has accepted into the pipeline."""

    payment: models.Pacs008Payment
    xml: bytes
    status: str
    transfer_id: str | None = None


class Participant(Protocol):
    """What SimNow needs from a bank. Implemented by ``agentbank_ledger.bank.Bank``."""

    response_delay_s: float

    @property
    def routing(self) -> str: ...

    @property
    def bank_id(self) -> str: ...

    def account_exists(self, number: str) -> bool: ...

    def on_credit_settled(self, payment: models.Pacs008Payment) -> None: ...

    def on_cancellation(self, req: models.Camt056CancellationRequest) -> ReturnDecision: ...

    def on_return_settled(self, original: models.Pacs008Payment, amount: int) -> None: ...

    def on_return_received(self, original: models.Pacs008Payment, amount: int) -> None: ...

    def release_return_hold(self, uetr: str) -> None: ...

    def on_rfp(self, rfp: models.Pain013Rfp) -> None: ...

    def on_rfp_status(self, status: models.Pain014RfpStatus) -> None: ...


@dataclass
class SimNow:
    """The instant-payment switch."""

    settlement: SettlementLedger
    participants: dict[str, Participant]
    limits: dict[str, int]
    network_limit_minor: int
    rules: UsageRuleValidator
    timeout_s: float = 20.0
    moment: datetime = field(default_factory=lambda: datetime(2026, 10, 29, 15, 0))
    archive: list[ArchivedMessage] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    prev_hash: bytes = _ZERO
    seen_msg: set[str] = field(default_factory=set)
    seen_e2e: set[str] = field(default_factory=set)
    seen_uetr: set[str] = field(default_factory=set)
    payments: dict[str, StoredPayment] = field(default_factory=dict)
    rfps: dict[str, tuple[str, str]] = field(default_factory=dict)
    fault: str | None = None
    _seq: int = 0

    def set_moment(self, moment: datetime) -> None:
        self.moment = moment

    def inject_fault(self, kind: str | None) -> None:
        """Admin fault injection: ``reject``, ``delay``, or ``None`` to clear."""
        self.fault = kind

    def submit(self, xml: bytes) -> SwitchReply:
        """Validate and process one enveloped ISO 20022 message."""
        started = time.perf_counter()
        reply = self._dispatch(xml)
        return SwitchReply(
            tx_status=reply.tx_status,
            reason_code=reply.reason_code,
            pacs002_xml=reply.pacs002_xml,
            elapsed_s=time.perf_counter() - started,
            detail=reply.detail,
        )

    def hash_chain_ok(self) -> bool:
        """Recompute the chain from the archived bytes."""
        prev = _ZERO
        for record in self.archive:
            digest = hashlib.sha256(prev + c14n(record.xml)).digest()
            if digest != record.hash:
                return False
            prev = digest
        return prev == self.prev_hash

    def save(self, path: Path) -> None:
        payload = {
            "prev_hash": self.prev_hash.hex(),
            "timeout_s": self.timeout_s,
            "limits": self.limits,
            "seen_msg": sorted(self.seen_msg),
            "seen_e2e": sorted(self.seen_e2e),
            "seen_uetr": sorted(self.seen_uetr),
            "fault": self.fault,
            "rfps": {k: list(v) for k, v in sorted(self.rfps.items())},
            "archive": [
                {
                    "hash": rec.hash.hex(),
                    "xml_b64": base64.b64encode(rec.xml).decode("ascii"),
                    "message_id": rec.message_id,
                    "sender": rec.sender,
                }
                for rec in self.archive
            ],
            "payments": {
                uetr: {
                    "status": stored.status,
                    "xml_b64": base64.b64encode(stored.xml).decode("ascii"),
                    "transfer_id": stored.transfer_id,
                }
                for uetr, stored in sorted(self.payments.items())
            },
        }
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def load(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        self.prev_hash = bytes.fromhex(str(raw["prev_hash"]))
        self.timeout_s = float(raw["timeout_s"])
        limits = raw["limits"]
        assert isinstance(limits, dict)
        self.limits = {str(k): int(v) for k, v in limits.items()}
        self.seen_msg = set(str(x) for x in raw["seen_msg"])
        self.seen_e2e = set(str(x) for x in raw["seen_e2e"])
        self.seen_uetr = set(str(x) for x in raw["seen_uetr"])
        self.fault = str(raw["fault"]) if raw.get("fault") else None
        rfps = raw["rfps"]
        assert isinstance(rfps, dict)
        self.rfps = {str(k): (str(v[0]), str(v[1])) for k, v in rfps.items()}
        self.archive = []
        for rec in raw["archive"]:
            assert isinstance(rec, dict)
            self.archive.append(
                ArchivedMessage(
                    hash=bytes.fromhex(str(rec["hash"])),
                    xml=base64.b64decode(str(rec["xml_b64"])),
                    message_id=str(rec["message_id"]),
                    sender=str(rec["sender"]),
                )
            )
        self.payments = {}
        payments = raw["payments"]
        assert isinstance(payments, dict)
        for uetr, stored in payments.items():
            assert isinstance(stored, dict)
            xml = base64.b64decode(str(stored["xml_b64"]))
            self.payments[str(uetr)] = StoredPayment(
                payment=parsers.parse_pacs008(xml),
                xml=xml,
                status=str(stored["status"]),
                transfer_id=str(stored["transfer_id"]) if stored.get("transfer_id") else None,
            )

    # --- pipeline ---------------------------------------------------------- #
    def _dispatch(self, xml: bytes) -> SwitchReply:
        try:
            header, document = parsers.parse_envelope(xml)
        except Exception as exc:
            self._archive(xml, "unknown", "")
            return self._technical(str(exc))
        message_id = _message_id(document)
        sender = header.from_routing
        self.trace.append(f"simnow.to_switch.{self._bank_id(sender)}")
        self._archive(xml, message_id or "unknown", sender)
        if message_id is None:
            return self._technical("unrecognised document namespace")
        if self.fault == "reject":
            return self._status_xml(document, message_id, "RJCT", "FF01", "fault injected")
        problems = self._validated(_header_only(xml), "head.001.001.02")
        problems += self._validated(document, message_id)
        if problems:
            return self._status_xml(document, message_id, "RJCT", "FF01", problems)
        if message_id == "pacs.008.001.08":
            return self._pacs008(document, sender)
        if message_id == "pacs.004.001.10":
            return self._pacs004(document, sender)
        if message_id == "camt.056.001.08":
            return self._camt056(document, sender)
        if message_id == "pain.013.001.07":
            return self._pain013(document, sender)
        if message_id == "pain.014.001.07":
            return self._pain014(document, sender)
        if message_id == "camt.029.001.09":
            self._archive_note(document, message_id, sender)
            return SwitchReply("ACSC", None, b"", 0.0, "resolution archived")
        return self._technical(f"unsupported message {message_id}")

    def _pacs008(self, document: bytes, sender: str) -> SwitchReply:
        payment = parsers.parse_pacs008(document)
        if payment.debtor_agent != sender:
            return self._pacs002(payment, "RJCT", "FF01", "BAH Fr does not match debtor agent")
        duplicate = self._duplicate(payment.msg_id, payment.end_to_end_id, payment.uetr)
        if duplicate:
            return self._pacs002(payment, "RJCT", "AM05", duplicate)
        self._remember(payment.msg_id, payment.end_to_end_id, payment.uetr)
        limit_reason = self._over_limit(sender, payment.amount_minor)
        if limit_reason:
            return self._pacs002(payment, "RJCT", "AM02", limit_reason)
        creditor = self.participants.get(payment.creditor_agent)
        if creditor is None or payment.creditor_agent == sender:
            return self._pacs002(payment, "RJCT", "AC01", "creditor agent is not a participant")
        transfer_id = f"pacs008-{payment.uetr}"
        try:
            self.settlement.pending(
                transfer_id, sender, payment.creditor_agent, payment.amount_minor
            )
        except SettlementError as exc:
            return self._pacs002(payment, "RJCT", "AM04", str(exc))
        self.payments[payment.uetr] = StoredPayment(payment, document, "PENDING", transfer_id)
        self.trace.append(f"simnow.to_bank.{creditor.bank_id}")
        if self.fault == "delay" or creditor.response_delay_s > self.timeout_s:
            self.settlement.void(transfer_id)
            self.payments[payment.uetr].status = "RJCT"
            return self._pacs002(payment, "RJCT", "AB05", "receiver timeout")
        if not creditor.account_exists(payment.creditor_account):
            self.settlement.void(transfer_id)
            self.payments[payment.uetr].status = "RJCT"
            return self._pacs002(payment, "RJCT", "AC01", "creditor account is unknown")
        self.settlement.post(transfer_id)
        creditor.on_credit_settled(payment)
        self.payments[payment.uetr].status = "ACSC"
        return self._pacs002(payment, "ACSC", None, "")

    def _pacs004(self, document: bytes, sender: str) -> SwitchReply:
        returned = parsers.parse_pacs004(document)
        if returned.msg_id in self.seen_msg:
            return self._bare("RJCT", "AM05", "duplicate MsgId")
        original = self.payments.get(returned.orgnl_uetr)
        if original is None or original.status != "ACSC":
            return self._bare("RJCT", "FF01", "original payment is not settled")
        if sender != original.payment.creditor_agent:
            return self._bare("RJCT", "FF01", "return is not from the creditor agent")
        self.seen_msg.add(returned.msg_id)
        debtor = original.payment.debtor_agent
        creditor = original.payment.creditor_agent
        transfer_id = f"pacs004-{returned.msg_id}"
        try:
            self.settlement.pending(transfer_id, creditor, debtor, returned.returned_amount_minor)
        except SettlementError as exc:
            self.participants[creditor].release_return_hold(returned.orgnl_uetr)
            return self._bare("RJCT", "AM04", str(exc))
        self.trace.append(f"simnow.to_bank.{self._bank_id(debtor)}")
        self.settlement.post(transfer_id)
        self.participants[creditor].on_return_settled(
            original.payment, returned.returned_amount_minor
        )
        self.participants[debtor].on_return_received(
            original.payment, returned.returned_amount_minor
        )
        original.status = "RETURNED"
        return self._bare("ACSC", None, "return posted")

    def _camt056(self, document: bytes, sender: str) -> SwitchReply:
        req = parsers.parse_camt056(document)
        if req.assignment_id in self.seen_msg:
            return self._bare("RJCT", "AM05", "duplicate cancellation id")
        self.seen_msg.add(req.assignment_id)
        if req.assigner_routing != sender:
            return self._bare("RJCT", "FF01", "BAH Fr does not match assigner")
        creditor = self.participants.get(req.assignee_routing)
        if creditor is None:
            return self._bare("RJCT", "AC01", "assignee is not a participant")
        self.trace.append(f"simnow.to_bank.{creditor.bank_id}")
        decision = creditor.on_cancellation(req)
        if decision.deferred:
            return self._bare("PDNG", None, "return parked for the creditor")
        if decision.accept and decision.pacs004_xml is not None:
            reply = self._dispatch(decision.pacs004_xml)
            if reply.tx_status != "ACSC":
                creditor.release_return_hold(req.orgnl_uetr)
            return reply
        if decision.camt029_xml is not None:
            self._archive(decision.camt029_xml, "camt.029.001.09", creditor.routing)
            self.trace.append(f"simnow.to_bank.{self._bank_id(sender)}")
        return self._bare("RJCT", "CUST", "creditor rejected the return")

    def _pain013(self, document: bytes, sender: str) -> SwitchReply:
        rfp = parsers.parse_pain013(document)
        if rfp.msg_id in self.seen_msg or rfp.end_to_end_id in self.seen_e2e:
            return self._bare("RJCT", "AM05", "duplicate request for payment")
        self.seen_msg.add(rfp.msg_id)
        self.seen_e2e.add(rfp.end_to_end_id)
        if rfp.creditor_agent != sender:
            return self._bare("RJCT", "FF01", "RfP is not from the creditor agent")
        debtor = self.participants.get(rfp.debtor_agent)
        if debtor is None:
            return self._bare("RJCT", "AC01", "debtor agent is not a participant")
        self.rfps[rfp.end_to_end_id] = (rfp.debtor_agent, rfp.creditor_agent)
        self.trace.append(f"simnow.to_bank.{debtor.bank_id}")
        debtor.on_rfp(rfp)
        return self._bare("ACSC", None, "request for payment forwarded")

    def _pain014(self, document: bytes, sender: str) -> SwitchReply:
        status = parsers.parse_pain014(document)
        if status.msg_id in self.seen_msg:
            return self._bare("RJCT", "AM05", "duplicate RfP status")
        self.seen_msg.add(status.msg_id)
        pair = self.rfps.get(status.orgnl_end_to_end_id)
        if pair is None:
            return self._bare("RJCT", "FF01", "unknown request for payment")
        debtor_routing, creditor_routing = pair
        if sender != debtor_routing:
            return self._bare("RJCT", "FF01", "RfP status is not from the debtor agent")
        creditor = self.participants[creditor_routing]
        self.trace.append(f"simnow.to_bank.{creditor.bank_id}")
        creditor.on_rfp_status(status)
        return self._bare("ACSC", None, "RfP status forwarded")

    # --- helpers ----------------------------------------------------------- #
    def _validated(self, xml: bytes, message_id: str) -> str:
        xsd = validate_xsd(xml, message_id)
        if not xsd.ok:
            return "; ".join(issue.reason for issue in xsd.issues) or "xsd rejected"
        usage = self.rules.validate(xml, message_id)
        if not usage.ok:
            return "; ".join(issue.reason for issue in usage.issues) or "usage rejected"
        return ""

    def _duplicate(self, msg_id: str, e2e: str, uetr: str) -> str:
        if msg_id in self.seen_msg:
            return "duplicate MsgId"
        if e2e in self.seen_e2e:
            return "duplicate EndToEndId"
        if uetr in self.seen_uetr:
            return "duplicate UETR"
        return ""

    def _remember(self, msg_id: str, e2e: str, uetr: str) -> None:
        self.seen_msg.add(msg_id)
        self.seen_e2e.add(e2e)
        self.seen_uetr.add(uetr)

    def _over_limit(self, routing: str, amount: int) -> str:
        if amount <= 0:
            return "amount must be positive"
        if amount > self.network_limit_minor:
            return "amount exceeds the network limit"
        limit = self.limits.get(routing)
        if limit is not None and amount > limit:
            return "amount exceeds the participant limit"
        return ""

    def _pacs002(
        self, payment: models.Pacs008Payment, status: str, code: str | None, detail: str
    ) -> SwitchReply:
        self._seq += 1
        addtl = (
            tuple(
                _latin_clip(detail, 105),
            )
            if detail and code
            else ()
        )
        report = models.Pacs002Status(
            msg_id=f"STS{self._seq:08d}",
            created_at=self.moment,
            orgnl_msg_id=payment.msg_id,
            orgnl_msg_nm_id="pacs.008.001.08",
            orgnl_end_to_end_id=payment.end_to_end_id,
            orgnl_uetr=payment.uetr,
            tx_status=status,
            status_reason_code=code,
            status_reason_addtl=addtl,
        )
        xml = builders.build_pacs002(report)
        wrapped = builders.envelope(
            models.BusinessHeader(
                from_routing=payment.creditor_agent,
                to_routing=payment.debtor_agent,
                biz_msg_idr=f"BAH{self._seq:08d}",
                msg_def_idr="pacs.002.001.10",
                created_at=self.moment,
            ),
            xml,
        )
        self._archive(wrapped, "pacs.002.001.10", payment.creditor_agent)
        self.trace.append(f"simnow.to_bank.{self._bank_id(payment.debtor_agent)}")
        return SwitchReply(status, code, wrapped, 0.0, detail)

    def _bare(self, status: str, code: str | None, detail: str) -> SwitchReply:
        return SwitchReply(status, code, b"", 0.0, detail)

    def _status_xml(
        self, document: bytes, message_id: str, status: str, code: str, detail: str
    ) -> SwitchReply:
        del document, message_id
        return self._bare(status, code, detail)

    def _technical(self, detail: str) -> SwitchReply:
        self._seq += 1
        xml = builders.build_admi002(
            models.Admi002Reject(
                related_ref=f"REJ{self._seq:08d}",
                rejecting_party_reason="X01",
                reason_description=_latin_clip(detail, 350),
            )
        )
        self._archive(xml, "admi.002.001.01", "")
        return SwitchReply("RJCT", "FF01", xml, 0.0, detail)

    def _archive(self, xml: bytes, message_id: str, sender: str) -> None:
        digest = hashlib.sha256(self.prev_hash + c14n(xml)).digest()
        self.prev_hash = digest
        self.archive.append(ArchivedMessage(digest, xml, message_id, sender))

    def _archive_note(self, xml: bytes, message_id: str, sender: str) -> None:
        del xml, message_id, sender

    def _bank_id(self, routing: str) -> str:
        participant = self.participants.get(routing)
        return participant.bank_id if participant is not None else routing


def _message_id(document: bytes) -> str | None:
    from agentbank_iso import message_id_of_xml

    return message_id_of_xml(document)


def _header_only(envelope_xml: bytes) -> bytes:
    from agentbank_iso._envelope import parse_envelope as split

    header_xml, _document = split(envelope_xml)
    return header_xml


def _latin_clip(text: str, limit: int) -> str:
    cleaned = "".join(ch if _latin_ok(ch) else " " for ch in text)
    cleaned = " ".join(cleaned.split()) or "rejected"
    return cleaned[:limit]


def _latin_ok(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in " /-?:().,'+")
