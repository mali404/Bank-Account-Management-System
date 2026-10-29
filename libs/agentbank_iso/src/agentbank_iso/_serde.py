"""xsdata (de)serialisation helpers shared by the builders and parsers.

A single serializer configuration is used everywhere so that output is
byte-stable: no pretty-printing, UTF-8, an XML declaration, and the message's
namespace bound as the default namespace.
"""

from __future__ import annotations

from xsdata.formats.dataclass.context import XmlContext
from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.parsers.config import ParserConfig
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from .errors import ParseError
from .messages import (
    document_class,
    get_spec,
    iter_specs,
    spec_for_namespace,
)

__all__ = ["from_xml", "serialize", "to_xml"]

# One shared context/serializer keeps model metadata compiled once.
_CONTEXT = XmlContext()
_SERIALIZER = XmlSerializer(
    context=_CONTEXT,
    config=SerializerConfig(xml_declaration=True, encoding="UTF-8", indent=""),
)
_PARSER = XmlParser(context=_CONTEXT, config=ParserConfig(fail_on_unknown_properties=True))


def serialize(document: object, namespace: str) -> bytes:
    """Serialise an xsdata document to UTF-8 bytes with ``namespace`` as default."""
    text = _SERIALIZER.render(document, ns_map={None: namespace})
    return text.encode("utf-8")


def to_xml(document: object) -> bytes:
    """Serialise any §6.1 binding instance, inferring its namespace from the type.

    The document's module name maps back to a registered message, so callers do
    not have to pass the namespace explicitly.
    """
    cls = type(document)
    for spec in iter_specs():
        if cls is document_class(spec.message_id):
            return serialize(document, spec.namespace)
    raise ParseError(f"unknown document type {cls.__name__!r} from {cls.__module__!r}")


def from_xml(xml: bytes, message_id: str) -> object:
    """Parse ``xml`` into the root binding class registered for ``message_id``."""
    spec = get_spec(message_id)
    cls = document_class(message_id)
    try:
        return _PARSER.from_bytes(xml, cls)
    except Exception as exc:  # xsdata raises a variety of parse errors
        raise ParseError(f"could not parse {spec.message_id}: {exc}") from exc


def namespace_of_xml(xml: bytes) -> str | None:
    """Return the XML namespace of the document root, or ``None`` if unreadable."""
    import lxml.etree as ET

    try:
        root = ET.fromstring(xml)
    except ET.XMLSyntaxError:
        return None
    tag = root.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1 : tag.index("}")]
    return None


def message_id_of_xml(xml: bytes) -> str | None:
    """Return the §6.1 message id for ``xml`` based on its namespace."""
    ns = namespace_of_xml(xml)
    if ns is None:
        return None
    spec = spec_for_namespace(ns)
    return spec.message_id if spec is not None else None
