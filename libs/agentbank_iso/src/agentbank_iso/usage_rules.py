"""YAML-driven usage-rule validator for the SimNow switch (SPEC §5.3).

Loads ``config/switch/usage_rules.yaml`` and the participant registry and checks
an inbound message beyond the XSD: mandatory fields, ``ChrgBr=SLEV``, one tx per
message, ``IntrBkSttlmDt`` equal to today (clock injectable), currency USD,
nine-digit participant routing numbers, charset profile and per-field max
lengths. Results use the same :class:`~agentbank_iso.validate.Issue` type and
carry element paths. XSD validation remains the job of
:func:`~agentbank_iso.validate.validate_xsd`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import lxml.etree as ET
import yaml

from agentbank_common.timeutil import now_utc

from .charset import first_violation
from .validate import Issue, ValidationResult

__all__ = ["UsageRuleValidator"]

# Transaction container element per message, for the "one tx" rule.
_TX_ELEMENT: dict[str, str] = {
    "pacs.008.001.08": "CdtTrfTxInf",
    "pacs.004.001.10": "TxInf",
    "pain.013.001.07": "CdtTrfTx",
    "pain.001.001.09": "CdtTrfTxInf",
}


def _default_config_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "config" / "switch"


def _local(tag: object) -> str:
    if isinstance(tag, str):
        return tag.rsplit("}", 1)[-1]
    return ""


def _path(elem: ET._Element) -> str:
    parts = [_local(a.tag) for a in reversed(list(elem.iterancestors()))]
    parts.append(_local(elem.tag))
    return "/" + "/".join(parts)


@dataclass(frozen=True)
class _FreeText:
    leaf: str
    max_length: int


class UsageRuleValidator:
    """Validate messages against the switch usage rules."""

    def __init__(
        self,
        config: dict[str, Any],
        participants: frozenset[str],
        clock: Callable[[], date] | None = None,
    ) -> None:
        self._config = config
        self._participants = participants
        self._clock = clock or (lambda: now_utc().date())

    @classmethod
    def from_config(
        cls,
        config_dir: Path | None = None,
        clock: Callable[[], date] | None = None,
    ) -> UsageRuleValidator:
        """Load the usage rules and participant registry from ``config/switch``."""
        directory = config_dir or _default_config_dir()
        config = yaml.safe_load((directory / "usage_rules.yaml").read_text(encoding="utf-8"))
        registry = yaml.safe_load((directory / "participants.yaml").read_text(encoding="utf-8"))
        routings = frozenset(str(p["routing"]) for p in registry.get("participants", []))
        return cls(config=config, participants=routings, clock=clock)

    @property
    def version(self) -> int:
        return int(self._config.get("version", 0))

    def validate(self, xml: bytes, message_id: str) -> ValidationResult:
        """Validate ``xml`` (already XSD-valid) against the usage rules."""
        try:
            root = ET.fromstring(xml)
        except ET.XMLSyntaxError as exc:
            return ValidationResult(
                ok=False,
                message_id=message_id,
                issues=(Issue(path="/", reason=f"malformed XML: {exc}", rule="xml:wellformed"),),
            )

        rules = self._config.get("messages", {}).get(message_id, {})
        defaults = self._config.get("defaults", {})
        issues: list[Issue] = []
        issues += self._check_mandatory(root, rules)
        issues += self._check_charge_bearer(root, rules)
        issues += self._check_single_tx(root, message_id, rules)
        issues += self._check_settlement_date(root)
        issues += self._check_currency(root, defaults)
        issues += self._check_routing(root)
        issues += self._check_free_text(root, rules, defaults)
        return ValidationResult(ok=not issues, message_id=message_id, issues=tuple(issues))

    # --- individual rules -------------------------------------------------- #
    def _check_mandatory(self, root: ET._Element, rules: dict[str, Any]) -> list[Issue]:
        present = {_local(e.tag) for e in root.iter()}
        out = []
        for name in rules.get("mandatory_fields", []):
            if name not in present:
                out.append(
                    Issue(
                        path=_path(root),
                        reason=f"mandatory field {name} is missing",
                        rule="usage:mandatory",
                        value=name,
                    )
                )
        return out

    def _check_charge_bearer(self, root: ET._Element, rules: dict[str, Any]) -> list[Issue]:
        expected = rules.get("charge_bearer")
        if not expected:
            return []
        out = []
        for elem in _find(root, "ChrgBr"):
            if (elem.text or "") != expected:
                out.append(
                    Issue(
                        path=_path(elem),
                        reason=f"ChrgBr must be {expected}",
                        rule="usage:chargeBearer",
                        value=elem.text,
                    )
                )
        return out

    def _check_single_tx(
        self, root: ET._Element, message_id: str, rules: dict[str, Any]
    ) -> list[Issue]:
        max_tx = rules.get("max_tx_per_message")
        element = _TX_ELEMENT.get(message_id)
        if max_tx is None or element is None:
            return []
        count = len(list(_find(root, element)))
        if count > max_tx:
            return [
                Issue(
                    path=_path(root),
                    reason=f"{count} {element} present; at most {max_tx} allowed",
                    rule="usage:maxTx",
                    value=str(count),
                )
            ]
        return []

    def _check_settlement_date(self, root: ET._Element) -> list[Issue]:
        today = self._clock().isoformat()
        out = []
        for elem in _find(root, "IntrBkSttlmDt"):
            if (elem.text or "") != today:
                out.append(
                    Issue(
                        path=_path(elem),
                        reason=f"IntrBkSttlmDt must be today ({today})",
                        rule="usage:settlementDate",
                        value=elem.text,
                    )
                )
        return out

    def _check_currency(self, root: ET._Element, defaults: dict[str, Any]) -> list[Issue]:
        expected = defaults.get("currency", "USD")
        out = []
        for elem in root.iter():
            ccy = elem.get("Ccy")
            if ccy is not None and ccy != expected:
                out.append(
                    Issue(
                        path=_path(elem),
                        reason=f"currency must be {expected}",
                        rule="usage:currency",
                        value=ccy,
                    )
                )
        return out

    def _check_routing(self, root: ET._Element) -> list[Issue]:
        routing = self._config.get("routing", {})
        digits = int(routing.get("digits", 9))
        must_be = bool(routing.get("must_be_participant", True))
        out = []
        for elem in _find(root, "MmbId"):
            value = elem.text or ""
            if not (value.isdigit() and len(value) == digits):
                out.append(
                    Issue(
                        path=_path(elem),
                        reason=f"routing number must be {digits} digits",
                        rule="usage:routing",
                        value=value,
                    )
                )
            elif must_be and value not in self._participants:
                out.append(
                    Issue(
                        path=_path(elem),
                        reason="routing number is not a registered participant",
                        rule="usage:routing",
                        value=value,
                    )
                )
        return out

    def _check_free_text(
        self, root: ET._Element, rules: dict[str, Any], defaults: dict[str, Any]
    ) -> list[Issue]:
        profile = rules.get("charset_profile", defaults.get("charset_profile", "latin"))
        fields = [
            _FreeText(leaf=str(f["label"]).rsplit("/", 1)[-1], max_length=int(f["max_length"]))
            for f in rules.get("free_text", [])
        ]
        limits: dict[str, int] = {}
        for f in fields:
            limits[f.leaf] = max(limits.get(f.leaf, 0), f.max_length)
        out = []
        for leaf, max_length in limits.items():
            for elem in _find(root, leaf):
                text = elem.text or ""
                if len(text) > max_length:
                    out.append(
                        Issue(
                            path=_path(elem),
                            reason=f"{leaf} exceeds {max_length} characters",
                            rule="usage:maxLength",
                            value=str(len(text)),
                        )
                    )
                violation = first_violation(text, profile)
                if violation is not None:
                    out.append(
                        Issue(
                            path=_path(elem),
                            reason=(
                                f"character {violation.display} not allowed by "
                                f"charset profile {profile!r}"
                            ),
                            rule="usage:charset",
                            value=violation.display,
                        )
                    )
        return out


def _find(root: ET._Element, local_name: str) -> Iterator[ET._Element]:
    for elem in root.iter():
        if _local(elem.tag) == local_name:
            yield elem
