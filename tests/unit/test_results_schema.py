"""The results-row schema must match SPEC §19 exactly (stable interface)."""

from __future__ import annotations

from agentbank_common.results_schema import RESULTS_COLUMN_NAMES, RESULTS_COLUMNS

# Transcribed verbatim from SPEC §19 ("Results row (parquet)").
SPEC_ORDER = (
    "run_id",
    "ts_utc",
    "git_sha",
    "model",
    "model_version",
    "framework",
    "defense_profile",
    "scenario_id",
    "task_id",
    "template_id",
    "seed",
    "injected",
    "attack_success",
    "utility_success",
    "harm",
    "utv_usd",
    "leaked_canaries",
    "hitl_prompts",
    "hitl_approved",
    "detected",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_s",
    "tool_calls",
    "error",
)

SPEC_TYPES = {
    "seed": "int",
    "injected": "bool",
    "attack_success": "bool",
    "utility_success": "bool",
    "harm": "bool",
    "utv_usd": "float",
    "leaked_canaries": "int",
    "hitl_prompts": "int",
    "hitl_approved": "int",
    "detected": "bool",
    "tokens_in": "int",
    "tokens_out": "int",
    "cost_usd": "float",
    "latency_s": "float",
    "tool_calls": "int",
}


def test_column_order_matches_spec() -> None:
    assert RESULTS_COLUMN_NAMES == SPEC_ORDER


def test_declared_types_match_spec() -> None:
    types = {c.name: c.type for c in RESULTS_COLUMNS}
    for name, expected in SPEC_TYPES.items():
        assert types[name] == expected


def test_no_duplicate_columns() -> None:
    assert len(RESULTS_COLUMN_NAMES) == len(set(RESULTS_COLUMN_NAMES))
