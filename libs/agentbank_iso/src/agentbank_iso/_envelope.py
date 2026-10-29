"""BAH + Document envelope used for switch traffic.

The switch moves a Business Application Header (head.001) alongside the business
message. We wrap both in a small testbed envelope element so a single blob can
carry the pair; each child keeps its own ISO namespace and can be validated
independently.
"""

from __future__ import annotations

import lxml.etree as ET

from ._serde import message_id_of_xml
from .errors import ParseError

__all__ = ["ENVELOPE_NS", "parse_envelope", "wrap_envelope"]

ENVELOPE_NS = "urn:agentbank:simnow:envelope:1"


def wrap_envelope(header_xml: bytes, document_xml: bytes) -> bytes:
    """Return ``<Envelope><AppHdr/><Document/></Envelope>`` bytes."""
    # lxml-stubs does not model the None (default-namespace) key in nsmap.
    root = ET.Element(f"{{{ENVELOPE_NS}}}Envelope", nsmap={None: ENVELOPE_NS})  # type: ignore[dict-item]
    root.append(_parse_child(header_xml))
    root.append(_parse_child(document_xml))
    return ET.tostring(root, xml_declaration=True, encoding="UTF-8")


def parse_envelope(xml: bytes) -> tuple[bytes, bytes]:
    """Split an envelope into ``(header_xml, document_xml)`` byte strings.

    The document half is returned verbatim so the caller can dispatch on its
    message id (see :func:`agentbank_iso._serde.message_id_of_xml`).
    """
    try:
        root = ET.fromstring(xml)
    except ET.XMLSyntaxError as exc:
        raise ParseError(f"malformed envelope: {exc}") from exc
    if root.tag != f"{{{ENVELOPE_NS}}}Envelope":
        raise ParseError(f"not an envelope: root is {root.tag!r}")
    children = list(root)
    if len(children) != 2:
        raise ParseError(f"envelope must have exactly 2 children, found {len(children)}")
    header_xml = ET.tostring(children[0], xml_declaration=True, encoding="UTF-8")
    document_xml = ET.tostring(children[1], xml_declaration=True, encoding="UTF-8")
    return header_xml, document_xml


def document_message_id(xml: bytes) -> str | None:
    """Convenience: the §6.1 message id of an envelope's document half."""
    _, document_xml = parse_envelope(xml)
    return message_id_of_xml(document_xml)


def _parse_child(xml: bytes) -> ET._Element:
    try:
        return ET.fromstring(xml)
    except ET.XMLSyntaxError as exc:
        raise ParseError(f"malformed envelope child: {exc}") from exc
