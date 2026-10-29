"""ISO 20022 bindings, builders, parsers, validation and injection helpers.

Public API (SPEC §6.1/§6.2):

* :mod:`agentbank_iso.messages` — registry of the §6.1 message set.
* :mod:`agentbank_iso.models` — typed domain models.
* :mod:`agentbank_iso.builders` — ``build_<msg>(model) -> bytes`` and ``envelope``.
* :mod:`agentbank_iso.parsers` — ``parse_<msg>(xml) -> model`` and ``parse_envelope``.
* :mod:`agentbank_iso.validate` — ``validate_xsd`` returning field-pathed issues.
* :mod:`agentbank_iso.usage_rules` — YAML-driven switch usage-rule validator.
* :mod:`agentbank_iso.inject` — injection helpers and charset analysis.
"""

from __future__ import annotations

from . import builders, inject, messages, models, parsers
from ._envelope import ENVELOPE_NS, parse_envelope, wrap_envelope
from ._serde import from_xml, message_id_of_xml, to_xml
from .builders import (
    build_admi002,
    build_camt029,
    build_camt052,
    build_camt053,
    build_camt054,
    build_camt056,
    build_head001,
    build_pacs002,
    build_pacs004,
    build_pacs008,
    build_pacs028,
    build_pain001,
    build_pain002,
    build_pain013,
    build_pain014,
    envelope,
)
from .errors import BuildError, FieldLengthError, IsoError, ParseError
from .parsers import (
    parse_admi002,
    parse_camt029,
    parse_camt052,
    parse_camt053,
    parse_camt054,
    parse_camt056,
    parse_head001,
    parse_pacs002,
    parse_pacs004,
    parse_pacs008,
    parse_pacs028,
    parse_pain001,
    parse_pain002,
    parse_pain013,
    parse_pain014,
)
from .usage_rules import UsageRuleValidator
from .validate import Issue, ValidationResult, validate_xsd

__version__ = "0.1.0"

__all__ = [
    "ENVELOPE_NS",
    "BuildError",
    "FieldLengthError",
    "IsoError",
    "Issue",
    "ParseError",
    "UsageRuleValidator",
    "ValidationResult",
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
    "builders",
    "envelope",
    "from_xml",
    "inject",
    "message_id_of_xml",
    "messages",
    "models",
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
    "parsers",
    "to_xml",
    "validate_xsd",
    "wrap_envelope",
]
