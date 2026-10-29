"""XSD validation with field paths, built on xmlschema with an lxml fast path.

:func:`validate_xsd` returns a :class:`ValidationResult` rather than raising, so
malformed XML, a wrong namespace or an unknown message all come back as
structured issues with an element ``path``, a ``reason``, an XSD ``rule`` and the
offending (truncated) value. Compiled schemas are cached per message id; the
common valid case short-circuits through lxml before xmlschema is consulted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

import lxml.etree as ET
import xmlschema

from ._serde import namespace_of_xml
from .messages import get_spec, spec_for_namespace, xsd_dir

__all__ = ["Issue", "ValidationResult", "validate_xsd"]

_MAX_VALUE_LEN = 64

_FACET_RULES: dict[str, str] = {
    "XsdMaxLengthFacet": "xsd:maxLength",
    "XsdMinLengthFacet": "xsd:minLength",
    "XsdLengthFacet": "xsd:length",
    "XsdPatternFacets": "xsd:pattern",
    "XsdEnumerationFacets": "xsd:enumeration",
    "XsdMaxInclusiveFacet": "xsd:maxInclusive",
    "XsdMinInclusiveFacet": "xsd:minInclusive",
    "XsdMaxExclusiveFacet": "xsd:maxExclusive",
    "XsdMinExclusiveFacet": "xsd:minExclusive",
    "XsdFractionDigitsFacet": "xsd:fractionDigits",
    "XsdTotalDigitsFacet": "xsd:totalDigits",
}


@dataclass(frozen=True)
class Issue:
    """A single validation problem."""

    path: str
    reason: str
    rule: str
    value: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one document."""

    ok: bool
    message_id: str | None
    issues: tuple[Issue, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return self.ok


@cache
def _xsd_schema(message_id: str) -> xmlschema.XMLSchema:
    path = xsd_dir() / get_spec(message_id).xsd_file
    return xmlschema.XMLSchema(str(path))


@cache
def _lxml_schema(message_id: str) -> ET.XMLSchema:
    path = xsd_dir() / get_spec(message_id).xsd_file
    return ET.XMLSchema(ET.parse(str(path)))


def validate_xsd(xml: bytes, message_id: str | None = None) -> ValidationResult:
    """Validate ``xml`` against its XSD, inferring the message from its namespace.

    When ``message_id`` is given it must match the document's namespace; a
    mismatch is reported rather than raised.
    """
    try:
        root = ET.fromstring(xml)
    except (ET.XMLSyntaxError, ValueError) as exc:
        return ValidationResult(
            ok=False,
            message_id=message_id,
            issues=(Issue(path="/", reason=f"malformed XML: {exc}", rule="xml:wellformed"),),
        )

    namespace = namespace_of_xml(xml)
    detected = spec_for_namespace(namespace) if namespace is not None else None

    if message_id is None:
        if detected is None:
            return ValidationResult(
                ok=False,
                message_id=None,
                issues=(
                    Issue(
                        path="/",
                        reason=f"unknown or unsupported message namespace {namespace!r}",
                        rule="iso:namespace",
                    ),
                ),
            )
        message_id = detected.message_id
    else:
        expected = get_spec(message_id).namespace
        if namespace != expected:
            return ValidationResult(
                ok=False,
                message_id=message_id,
                issues=(
                    Issue(
                        path="/",
                        reason=f"wrong namespace {namespace!r}; expected {expected!r}",
                        rule="iso:namespace",
                    ),
                ),
            )

    # Fast path: lxml says valid -> done, no xmlschema pass needed.
    if _lxml_schema(message_id).validate(root):
        return ValidationResult(ok=True, message_id=message_id)

    issues = tuple(_issue(err) for err in _xsd_schema(message_id).iter_errors(xml))
    if not issues:  # lxml and xmlschema disagreed; surface a generic failure
        issues = (Issue(path="/", reason="document failed XSD validation", rule="xsd:validation"),)
    return ValidationResult(ok=False, message_id=message_id, issues=issues)


def _issue(err: xmlschema.XMLSchemaValidationError) -> Issue:
    path = err.path or "/"
    reason = " ".join(str(err.reason or "invalid value").split())
    return Issue(path=path, reason=reason, rule=_rule(err), value=_offending_value(err))


def _rule(err: xmlschema.XMLSchemaValidationError) -> str:
    name = type(err.validator).__name__
    if name in _FACET_RULES:
        return _FACET_RULES[name]
    if "Element" in name or "Group" in name or "Model" in name:
        return "xsd:content"
    if "Atomic" in name or "Builtin" in name or "Union" in name:
        return "xsd:type"
    return "xsd:validation"


def _offending_value(err: xmlschema.XMLSchemaValidationError) -> str | None:
    value = getattr(err, "value", None)
    if value is None and err.elem is not None:
        value = err.elem.text
    if value is None:
        return None
    text = str(value)
    if len(text) > _MAX_VALUE_LEN:
        return text[:_MAX_VALUE_LEN] + "…"
    return text
