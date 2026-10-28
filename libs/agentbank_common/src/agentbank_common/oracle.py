"""Typed placeholders for the oracle interface (SPEC §19).

The concrete state capture and oracle functions arrive with ``bankbench`` in
milestone M5. These dataclasses pin the stable signature now so defenses and
scenarios can be typed against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["OracleResult", "StateSnapshot"]


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Before/after view of system state used by oracles (SPEC §19).

    Each field holds an opaque, serialisable diff of one state store. The
    concrete shapes are defined in M2/M5; here they are typed as mappings so the
    interface is stable and inspectable.
    """

    bank_db: dict[str, Any] = field(default_factory=dict)
    tigerbeetle: dict[str, Any] = field(default_factory=dict)
    switch_archive: dict[str, Any] = field(default_factory=dict)
    mail_outbox: dict[str, Any] = field(default_factory=dict)
    psp_egress: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OracleResult:
    """Outcome of an oracle evaluation over a :class:`StateSnapshot`."""

    success: bool
    evidence: dict[str, Any] = field(default_factory=dict)
