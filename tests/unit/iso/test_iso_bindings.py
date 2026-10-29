"""Every §6.1 message exposes an importable root binding class."""

from __future__ import annotations

import pytest

from agentbank_iso.messages import all_message_ids, document_class, get_spec


@pytest.mark.parametrize("message_id", all_message_ids())
def test_root_class_importable(message_id: str) -> None:
    spec = get_spec(message_id)
    cls = document_class(message_id)
    assert cls.__name__ == spec.root_tag or (
        spec.root_tag == "Document" and cls.__name__ == "Document"
    )
    # dataclass instances can be constructed empty (all fields keyword-only).
    assert hasattr(cls, "__dataclass_fields__")


def test_fifteen_messages() -> None:
    assert len(all_message_ids()) == 15
