"""Three banks plus the SimNow switch, and the snapshot used by ``make reset``.

The anchor date is 2026-10-29 so a seeded world does not depend on the wall
clock: usage rules compare ``IntrBkSttlmDt`` with this date, and ``set_today``
moves it when the generator posts historical payments.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import yaml

from agentbank_iso.usage_rules import UsageRuleValidator

from .bank import Bank, BankProfile
from .settlement import SettlementLedger
from .simnow import SimNow

__all__ = ["ANCHOR", "PREFUND_MINOR", "World"]

ANCHOR = date(2026, 10, 29)
PREFUND_MINOR = 200_000_000  # $2,000,000.00 per bank, in cents
_NOON = time(15, 0)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


class World:
    """An in-process deployment of the three banks and the switch."""

    def __init__(
        self, root: Path, today: date | None = None, config_dir: Path | None = None
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._today = today or ANCHOR
        repo = config_dir or (_repo_root() / "config")
        profiles = _load_profiles(repo / "banks")
        limits, network, timeout_s = _load_switch(repo / "switch")
        self.banks = {
            profile.id: Bank(
                profile,
                root / f"{profile.id}.sqlite",
                clock=lambda: self._today,
                moment=self._moment,
            )
            for profile in profiles
        }
        self.settlement = SettlementLedger()
        self.settlement.create_account("treasury")
        for bank in self.banks.values():
            self.settlement.create_account(bank.routing)
            self.settlement.fund(bank.routing, PREFUND_MINOR)
            bank.open_books(PREFUND_MINOR)
        self.switch = SimNow(
            settlement=self.settlement,
            participants={bank.routing: bank for bank in self.banks.values()},
            limits=limits,
            network_limit_minor=network,
            rules=UsageRuleValidator.from_config(repo / "switch", clock=lambda: self._today),
            timeout_s=float(timeout_s),
            moment=self._moment(),
        )
        for bank in self.banks.values():
            bank.switch = self.switch

    @classmethod
    def create(cls, root: Path, today: date | None = None) -> World:
        return cls(root, today)

    def bank(self, bank_id: str) -> Bank:
        return self.banks[bank_id]

    def set_today(self, day: date) -> None:
        self._today = day
        self.switch.set_moment(self._moment())

    def check_invariants(self) -> list[str]:
        """Ledger sum, settlement GL versus switch position, clear suspense, hash chain."""
        errors: list[str] = []
        if self.settlement.positions_sum() != 0:
            errors.append(f"settlement positions sum to {self.settlement.positions_sum()}")
        for bank in self.banks.values():
            errors.extend(f"{bank.bank_id}: {item}" for item in bank.books.invariant_errors())
            general_ledger = bank.books.settlement_position()
            position = self.settlement.position(bank.routing)
            if general_ledger != position:
                errors.append(
                    f"{bank.bank_id} settlement GL {general_ledger} != position {position}"
                )
            if bank.books.suspense_balance() != 0:
                errors.append(f"{bank.bank_id} suspense is {bank.books.suspense_balance()}")
        if not self.switch.hash_chain_ok():
            errors.append("switch hash chain does not verify")
        return errors

    def canonical(self) -> bytes:
        """Byte-stable dump of balances, customers and the archive head."""
        payload: dict[str, Any] = {"anchor": self._today.isoformat(), "banks": {}}
        for bank_id in sorted(self.banks):
            bank = self.banks[bank_id]
            payload["banks"][bank_id] = {
                "customers": [_plain(row) for row in bank.books.customers()],
                "accounts": [
                    {**_plain(row), "balance": bank.books.net_credit(str(row["id"]))}
                    for row in bank.books.all_accounts()
                ],
                "payments": [_plain(row) for row in bank.books.payments_rows()],
                "position": self.settlement.position(bank.routing),
            }
        payload["archive_len"] = len(self.switch.archive)
        payload["archive_head"] = self.switch.prev_hash.hex()
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def mark_snapshot(self) -> None:
        """Copy the current books and ledgers to ``root/snapshot`` (the reset image)."""
        self._flush()
        self._close()
        snap = self.root / "snapshot"
        if snap.exists():
            shutil.rmtree(snap)
        snap.mkdir()
        for path in self.root.iterdir():
            if path.is_file():
                shutil.copy(path, snap / path.name)
        self._reopen()

    def reset(self) -> float:
        """Restore the snapshot. Returns elapsed seconds (the M2 budget is 30)."""
        import time

        started = time.perf_counter()
        snap = self.root / "snapshot"
        if not snap.is_dir():
            raise FileNotFoundError(f"no snapshot at {snap}; seed the world first")
        self._close()
        for path in snap.iterdir():
            if path.is_file():
                shutil.copy(path, self.root / path.name)
        self._reopen()
        self.settlement.load(self.root / "settlement.json")
        self.switch.settlement = self.settlement
        self.switch.load(self.root / "switch.json")
        return time.perf_counter() - started

    def _moment(self) -> datetime:
        return datetime.combine(self._today, _NOON, tzinfo=UTC)

    def _flush(self) -> None:
        self.settlement.save(self.root / "settlement.json")
        self.switch.save(self.root / "switch.json")

    def _close(self) -> None:
        for bank in self.banks.values():
            bank.books.close()

    def _reopen(self) -> None:
        for bank in self.banks.values():
            bank.books.reopen()


def restore_tree(root: Path) -> float:
    """File-level reset used by ``make reset`` when no process is holding the files."""
    import time

    started = time.perf_counter()
    snap = root / "snapshot"
    if not snap.is_dir():
        raise FileNotFoundError(f"no snapshot at {snap}; run make seed first")
    for path in snap.iterdir():
        if path.is_file():
            shutil.copy(path, root / path.name)
    return time.perf_counter() - started


def _load_profiles(directory: Path) -> list[BankProfile]:
    profiles: list[BankProfile] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        profile = raw.get("profile", {})
        assert isinstance(profile, dict)
        profiles.append(
            BankProfile(
                id=str(raw["id"]),
                name=str(raw["name"]),
                routing=str(raw["routing"]),
                per_payment_limit_minor=int(profile["per_payment_limit_minor"]),
                daily_limit_minor=int(profile["daily_limit_minor"]),
                new_payee_cooling_hours=int(profile["new_payee_cooling_hours"]),
                name_check=bool(profile["name_check"]),
                step_up_threshold_minor=int(profile["step_up_threshold_minor"]),
                stricter_when_agent_initiated=bool(profile["stricter_when_agent_initiated"]),
                fapi_variant=str(profile.get("fapi_variant", "dpop")),
            )
        )
    return profiles


def _load_switch(directory: Path) -> tuple[dict[str, int], int, int]:
    registry = yaml.safe_load((directory / "participants.yaml").read_text(encoding="utf-8"))
    rules = yaml.safe_load((directory / "usage_rules.yaml").read_text(encoding="utf-8"))
    assert isinstance(registry, dict)
    assert isinstance(rules, dict)
    defaults = registry.get("defaults", {})
    assert isinstance(defaults, dict)
    limits: dict[str, int] = {}
    for row in registry.get("participants", []):
        assert isinstance(row, dict)
        limits[str(row["routing"])] = int(row["participant_limit_minor"])
    network = int(defaults["network_limit_minor"])
    timeout_s = int(rules.get("receiver_timeout_s", 20))
    return limits, network, timeout_s


def _plain(row: object) -> dict[str, object]:
    assert isinstance(row, dict)
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
