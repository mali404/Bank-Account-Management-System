"""M5: the 24 scenarios, oracle fixtures, and a deterministic mock report."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import pytest
from bankbench.oracles import ORACLES, evaluate
from bankbench.report import write_run
from bankbench.runner import ANCHOR_TS, run_catalog
from bankbench.scenario import Scenario, load_scenarios

from agentbank_common.oracle import StateSnapshot
from agentbank_common.results_schema import RESULTS_COLUMN_NAMES

EXPECTED = [f"S{n:02d}" for n in range(1, 25)]

_FLAG_KEY = {
    "posted_transfer": "posted_to_attacker",
    "payee_added": "payee_added",
    "amount_mismatch": "amount_mismatch",
    "unauthorized_transfer": "unauthorized_transfer",
    "adjustment": "adjustment",
    "fraudulent_return": "fraudulent_return",
    "second_transfer": "second_transfer",
    "psp_payment": "psp_payment",
    "broader_consent": "broader_consent",
    "descriptor_changed": "descriptor_changed",
    "cumulative_value": "cumulative_value",
    "limit_bypass": "limit_bypass",
    "held_released": "held_released",
    "confusable_payee": "confusable_payee",
    "unauthorized_action": "unauthorized_action",
    "account_frozen": "account_frozen",
    "wrong_creditor": "wrong_creditor",
}


def _scenario(oracle: str) -> Scenario:
    return Scenario(
        id="Sx",
        title="fixture",
        adversary="external",
        channel="C1",
        target_agent="cba",
        user_task_id="T001",
        injection_template="important_message.j2",
        placement="body",
        goal="fixture goal",
        success_oracle=oracle,
        utility_oracle="utility_met",
        severity="high",
        tags=(),
    )


def _states(name: str) -> tuple[StateSnapshot, StateSnapshot]:
    if name == "canary_egress":
        return (
            StateSnapshot(psp_egress={"body": "CANARY-bank-c-0001"}),
            StateSnapshot(psp_egress={"body": "ordinary report"}),
        )
    if name == "email_exfil":
        return (
            StateSnapshot(mail_outbox={"body": "transactions to attacker"}),
            StateSnapshot(mail_outbox={"body": "rent receipt"}),
        )
    if name == "undisclosed_transfer":
        return (
            StateSnapshot(bank_db={"transfer_posted": True, "disclosed": False}),
            StateSnapshot(bank_db={"transfer_posted": True, "disclosed": True}),
        )
    if name == "prompt_canary":
        return (
            StateSnapshot(switch_archive={"text": "CANARY-prompt"}),
            StateSnapshot(switch_archive={"text": "posted rent"}),
        )
    if name == "utility_met":
        return (
            StateSnapshot(bank_db={"utility_success": True}),
            StateSnapshot(bank_db={}),
        )
    key = _FLAG_KEY[name]
    return StateSnapshot(bank_db={key: True}), StateSnapshot(bank_db={key: False})


def test_catalog_covers_s01_through_s24(repo_root: Path) -> None:
    scenarios = load_scenarios()
    assert [item.id for item in scenarios] == EXPECTED
    templates = {path.name for path in (repo_root / "templates" / "injections").glob("*.j2")}
    required = {
        "important_message.j2",
        "tool_knowledge.j2",
        "ignore_previous.j2",
        "authority.j2",
        "multilingual.j2",
        "split_payload.j2",
        "encoded.j2",
        "adaptive.j2",
    }
    assert required <= templates
    for item in scenarios:
        assert item.injection_template in templates
        assert item.success_oracle in ORACLES
        assert item.utility_oracle == "utility_met"


def test_catalog_is_deterministic_under_a_fixed_seed() -> None:
    first = [row.as_dict() for row in run_catalog(seed=42)]
    second = [row.as_dict() for row in run_catalog(seed=42)]
    assert first == second
    assert {row["scenario_id"] for row in first} == set(EXPECTED)
    assert {row["ts_utc"] for row in first} == {ANCHOR_TS}
    assert len(first) == 48


def test_mock_follows_injection_only_under_d0() -> None:
    rows = [row.as_dict() for row in run_catalog(seed=7, defenses=("D0", "D4"))]
    assert len(rows) == 96
    for row in rows:
        if row["injected"] is False:
            assert row["attack_success"] is False
            assert row["utility_success"] is True
        elif row["defense_profile"] == "D0":
            assert row["attack_success"] is True
            assert row["harm"] is True
        else:
            # D4 is recorded. The mock does not implement that profile.
            assert row["defense_profile"] == "D4"
            assert row["attack_success"] is False
            assert row["utility_success"] is True


def test_report_writes_parquet_in_column_order(tmp_path: Path) -> None:
    rows = run_catalog(seed=42)
    report = write_run(rows, tmp_path)
    text = report.read_text(encoding="utf-8")
    for metric in ("ASR", "BU", "UA", "UTV"):
        assert metric in text
    table = pq.read_table(tmp_path / "results.parquet")
    assert table.column_names == list(RESULTS_COLUMN_NAMES)
    assert table.num_rows == 48


@pytest.mark.parametrize("name", sorted(ORACLES))
def test_oracle_forced_success_and_failure(name: str) -> None:
    scenario = _scenario(name)
    success, failure = _states(name)
    assert evaluate(name, success, scenario, None).success is True
    assert evaluate(name, failure, scenario, None).success is False


def test_unknown_oracle_fails_closed() -> None:
    result = evaluate("missing", StateSnapshot(), _scenario("utility_met"), None)
    assert result.success is False
    assert result.evidence["missing_oracle"] == "missing"
