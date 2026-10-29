"""Registry of the SPEC §6.1 ISO 20022 message set.

Each :class:`MessageSpec` records the message identifier, XML namespace, root
element, generated :mod:`agentbank_iso.gen` binding module, committed XSD file
and the attacker-controllable free-text fields called out in SPEC §6.1 (table
in §8 channels C3-C6, C12). The free-text paths are absolute element paths that
match both the XSD and the paths reported by :mod:`agentbank_iso.validate`, so
they double as the targets for the 140-character limit tests.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

__all__ = [
    "FreeTextField",
    "MessageSpec",
    "all_message_ids",
    "document_class",
    "get_spec",
    "iter_specs",
    "spec_for_namespace",
    "xsd_dir",
]

_NAMESPACE_PREFIX = "urn:iso:std:iso:20022:tech:xsd:"


@dataclass(frozen=True)
class FreeTextField:
    """An attacker-controllable free-text element (SPEC §6.1 / §8 channels)."""

    path: str
    """Absolute element path, e.g. ``/Document/.../RmtInf/Ustrd``."""
    max_length: int
    """The ``maxLength`` facet enforced by the XSD for this element."""
    label: str
    """Human label, e.g. ``"RmtInf/Ustrd"``."""


@dataclass(frozen=True)
class MessageSpec:
    """Static description of one SPEC §6.1 message."""

    message_id: str
    """Full identifier, e.g. ``"pacs.008.001.08"``."""
    short: str
    """Short identifier, e.g. ``"pacs.008"``."""
    area: str
    """Business area, e.g. ``"pacs"``."""
    root_tag: str
    """Root element local name (``"Document"`` for all but head.001's ``AppHdr``)."""
    module: str
    """Dotted path of the generated binding subpackage."""
    used_for: str
    """One-line purpose from SPEC §6.1."""
    free_text_fields: tuple[FreeTextField, ...] = ()

    @property
    def namespace(self) -> str:
        return f"{_NAMESPACE_PREFIX}{self.message_id}"

    @property
    def xsd_file(self) -> str:
        return f"{self.message_id}.xsd"


def _ft(path: str, max_length: int, label: str) -> FreeTextField:
    return FreeTextField(path=path, max_length=max_length, label=label)


# SPEC §6.1 message set. Order follows the spec table.
_SPECS: tuple[MessageSpec, ...] = (
    MessageSpec(
        message_id="head.001.001.02",
        short="head.001",
        area="head",
        root_tag="AppHdr",
        module="agentbank_iso.gen.head001_001_02",
        used_for="Business Application Header (envelope on switch traffic)",
    ),
    MessageSpec(
        message_id="pacs.008.001.08",
        short="pacs.008",
        area="pacs",
        root_tag="Document",
        module="agentbank_iso.gen.pacs008_001_08",
        used_for="FIToFICstmrCdtTrf — credit transfer",
        free_text_fields=(
            _ft("/Document/FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm", 140, "Dbtr/Nm"),
            _ft("/Document/FIToFICstmrCdtTrf/CdtTrfTxInf/Cdtr/Nm", 140, "Cdtr/Nm"),
            _ft("/Document/FIToFICstmrCdtTrf/CdtTrfTxInf/UltmtDbtr/Nm", 140, "UltmtDbtr/Nm"),
            _ft("/Document/FIToFICstmrCdtTrf/CdtTrfTxInf/RmtInf/Ustrd", 140, "RmtInf/Ustrd"),
            _ft(
                "/Document/FIToFICstmrCdtTrf/CdtTrfTxInf/RmtInf/Strd/AddtlRmtInf",
                140,
                "RmtInf/Strd/AddtlRmtInf",
            ),
            _ft(
                "/Document/FIToFICstmrCdtTrf/CdtTrfTxInf/InstrForCdtrAgt/InstrInf",
                140,
                "InstrForCdtrAgt/InstrInf",
            ),
        ),
    ),
    MessageSpec(
        message_id="pacs.002.001.10",
        short="pacs.002",
        area="pacs",
        root_tag="Document",
        module="agentbank_iso.gen.pacs002_001_10",
        used_for="FIToFIPmtStsRpt — ACSC/RJCT status",
        free_text_fields=(
            _ft(
                "/Document/FIToFIPmtStsRpt/TxInfAndSts/StsRsnInf/AddtlInf",
                105,
                "StsRsnInf/AddtlInf",
            ),
        ),
    ),
    MessageSpec(
        message_id="pacs.004.001.10",
        short="pacs.004",
        area="pacs",
        root_tag="Document",
        module="agentbank_iso.gen.pacs004_001_10",
        used_for="PmtRtr — return of funds",
        free_text_fields=(
            _ft("/Document/PmtRtr/TxInf/RtrRsnInf/AddtlInf", 105, "RtrRsnInf/AddtlInf"),
        ),
    ),
    MessageSpec(
        message_id="camt.056.001.08",
        short="camt.056",
        area="camt",
        root_tag="Document",
        module="agentbank_iso.gen.camt056_001_08",
        used_for="FIToFIPmtCxlReq — return/recall request",
        free_text_fields=(
            _ft(
                "/Document/FIToFIPmtCxlReq/Undrlyg/TxInf/CxlRsnInf/AddtlInf",
                105,
                "CxlRsnInf/AddtlInf",
            ),
        ),
    ),
    MessageSpec(
        message_id="camt.029.001.09",
        short="camt.029",
        area="camt",
        root_tag="Document",
        module="agentbank_iso.gen.camt029_001_09",
        used_for="RsltnOfInvstgtn — response to camt.056",
        free_text_fields=(
            _ft(
                "/Document/RsltnOfInvstgtn/CxlDtls/TxInfAndSts/CxlStsRsnInf/AddtlInf",
                105,
                "CxlStsRsnInf/AddtlInf",
            ),
        ),
    ),
    MessageSpec(
        message_id="pacs.028.001.03",
        short="pacs.028",
        area="pacs",
        root_tag="Document",
        module="agentbank_iso.gen.pacs028_001_03",
        used_for="FIToFIPmtStsReq — status inquiry",
    ),
    MessageSpec(
        message_id="pain.013.001.07",
        short="pain.013",
        area="pain",
        root_tag="Document",
        module="agentbank_iso.gen.pain013_001_07",
        used_for="CdtrPmtActvtnReq — request for payment (RfP)",
        free_text_fields=(
            _ft("/Document/CdtrPmtActvtnReq/PmtInf/CdtTrfTx/Cdtr/Nm", 140, "Cdtr/Nm"),
            _ft("/Document/CdtrPmtActvtnReq/PmtInf/CdtTrfTx/RmtInf/Ustrd", 140, "RmtInf/Ustrd"),
            _ft(
                "/Document/CdtrPmtActvtnReq/PmtInf/CdtTrfTx/InstrForCdtrAgt/InstrInf",
                140,
                "InstrForCdtrAgt/InstrInf",
            ),
        ),
    ),
    MessageSpec(
        message_id="pain.014.001.07",
        short="pain.014",
        area="pain",
        root_tag="Document",
        module="agentbank_iso.gen.pain014_001_07",
        used_for="CdtrPmtActvtnReqStsRpt — RfP response",
        free_text_fields=(
            _ft(
                "/Document/CdtrPmtActvtnReqStsRpt/OrgnlPmtInfAndSts/TxInfAndSts/StsRsnInf/AddtlInf",
                105,
                "StsRsnInf/AddtlInf",
            ),
        ),
    ),
    MessageSpec(
        message_id="pain.001.001.09",
        short="pain.001",
        area="pain",
        root_tag="Document",
        module="agentbank_iso.gen.pain001_001_09",
        used_for="CstmrCdtTrfInitn — customer/PSP initiation",
        free_text_fields=(
            _ft("/Document/CstmrCdtTrfInitn/PmtInf/CdtTrfTxInf/Cdtr/Nm", 140, "Cdtr/Nm"),
            _ft("/Document/CstmrCdtTrfInitn/PmtInf/CdtTrfTxInf/RmtInf/Ustrd", 140, "RmtInf/Ustrd"),
        ),
    ),
    MessageSpec(
        message_id="pain.002.001.10",
        short="pain.002",
        area="pain",
        root_tag="Document",
        module="agentbank_iso.gen.pain002_001_10",
        used_for="CstmrPmtStsRpt — status to initiator",
        free_text_fields=(
            _ft(
                "/Document/CstmrPmtStsRpt/OrgnlPmtInfAndSts/TxInfAndSts/StsRsnInf/AddtlInf",
                105,
                "StsRsnInf/AddtlInf",
            ),
        ),
    ),
    MessageSpec(
        message_id="camt.053.001.08",
        short="camt.053",
        area="camt",
        root_tag="Document",
        module="agentbank_iso.gen.camt053_001_08",
        used_for="BkToCstmrStmt — daily statement",
        free_text_fields=(
            _ft("/Document/BkToCstmrStmt/Stmt/Ntry/AddtlNtryInf", 500, "Ntry/AddtlNtryInf"),
            _ft(
                "/Document/BkToCstmrStmt/Stmt/Ntry/NtryDtls/TxDtls/RmtInf/Ustrd",
                140,
                "NtryDtls/TxDtls/RmtInf/Ustrd",
            ),
        ),
    ),
    MessageSpec(
        message_id="camt.054.001.08",
        short="camt.054",
        area="camt",
        root_tag="Document",
        module="agentbank_iso.gen.camt054_001_08",
        used_for="BkToCstmrDbtCdtNtfctn — credit/debit notification",
        free_text_fields=(
            _ft(
                "/Document/BkToCstmrDbtCdtNtfctn/Ntfctn/Ntry/AddtlNtryInf", 500, "Ntry/AddtlNtryInf"
            ),
            _ft(
                "/Document/BkToCstmrDbtCdtNtfctn/Ntfctn/Ntry/NtryDtls/TxDtls/RmtInf/Ustrd",
                140,
                "NtryDtls/TxDtls/RmtInf/Ustrd",
            ),
        ),
    ),
    MessageSpec(
        message_id="camt.052.001.08",
        short="camt.052",
        area="camt",
        root_tag="Document",
        module="agentbank_iso.gen.camt052_001_08",
        used_for="BkToCstmrAcctRpt — intraday position",
        free_text_fields=(
            _ft("/Document/BkToCstmrAcctRpt/Rpt/Ntry/AddtlNtryInf", 500, "Ntry/AddtlNtryInf"),
        ),
    ),
    MessageSpec(
        message_id="admi.002.001.01",
        short="admi.002",
        area="admi",
        root_tag="Document",
        module="agentbank_iso.gen.admi002_001_01",
        used_for="MessageReject — technical reject",
        free_text_fields=(_ft("/Document/admi.002.001.01/Rsn/RsnDesc", 350, "Rsn/RsnDesc"),),
    ),
)

_BY_ID: dict[str, MessageSpec] = {s.message_id: s for s in _SPECS}
_BY_NS: dict[str, MessageSpec] = {s.namespace: s for s in _SPECS}


def iter_specs() -> tuple[MessageSpec, ...]:
    """Return every message spec in SPEC §6.1 order."""
    return _SPECS


def all_message_ids() -> tuple[str, ...]:
    """Return every message identifier in SPEC §6.1 order."""
    return tuple(s.message_id for s in _SPECS)


def get_spec(message_id: str) -> MessageSpec:
    """Return the spec for ``message_id`` or raise :class:`KeyError`."""
    return _BY_ID[message_id]


def spec_for_namespace(namespace: str) -> MessageSpec | None:
    """Return the spec whose XML namespace is ``namespace``, else ``None``."""
    return _BY_NS.get(namespace)


@cache
def document_class(message_id: str) -> type:
    """Import and return the root binding class for ``message_id``."""
    spec = _BY_ID[message_id]
    module = importlib.import_module(spec.module)
    return getattr(module, spec.root_tag)  # type: ignore[no-any-return]


def xsd_dir() -> Path:
    """Return the path to the committed ``iso20022/xsd`` directory."""
    # libs/agentbank_iso/src/agentbank_iso/messages.py -> repo root is parents[4].
    return Path(__file__).resolve().parents[4] / "iso20022" / "xsd"


# Guard: free-text paths must sit under the correct root element.
for _spec in _SPECS:
    for _f in _spec.free_text_fields:
        assert _f.path.startswith(f"/{_spec.root_tag}/"), (_spec.message_id, _f.path)
