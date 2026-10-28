"""Tests for UUID / UETR / ISO 20022 identifier helpers."""

from __future__ import annotations

from random import Random

from agentbank_common.ids import (
    MAX_ISO_ID_LEN,
    is_valid_uetr,
    new_end_to_end_id,
    new_msg_id,
    new_uetr,
    new_uuid4,
)


def test_uuid_and_uetr_are_valid() -> None:
    assert is_valid_uetr(new_uetr())
    assert is_valid_uetr(new_uuid4())


def test_is_valid_uetr_rejects_bad() -> None:
    assert not is_valid_uetr("not-a-uuid")
    assert not is_valid_uetr("")
    # Version nibble must be 4.
    assert not is_valid_uetr("12345678-1234-1234-1234-123456789abc")


def test_iso_ids_respect_length() -> None:
    assert len(new_msg_id()) <= MAX_ISO_ID_LEN
    assert len(new_end_to_end_id()) <= MAX_ISO_ID_LEN
    assert new_msg_id().startswith("MSG")
    assert new_end_to_end_id().startswith("E2E")


def test_deterministic_with_seeded_random() -> None:
    assert new_uetr(Random(1)) == new_uetr(Random(1))
    assert new_msg_id(rng=Random(7)) == new_msg_id(rng=Random(7))
    assert new_uetr(Random(1)) != new_uetr(Random(2))
