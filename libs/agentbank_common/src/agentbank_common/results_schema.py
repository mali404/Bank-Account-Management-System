"""The stable ``results.parquet`` row schema (SPEC §19).

This column list is a stable interface: the order and names must not change
without a version bump. ``bankbench`` (milestone M5) writes rows matching this
schema; downstream analysis reads it.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

ColumnType = Literal["str", "int", "float", "bool"]

__all__ = ["RESULTS_COLUMNS", "RESULTS_COLUMN_NAMES", "ResultsColumn"]


class ResultsColumn(NamedTuple):
    """A single results-row column: its name and logical type."""

    name: str
    type: ColumnType


# Order matches SPEC §19 exactly.
RESULTS_COLUMNS: tuple[ResultsColumn, ...] = (
    ResultsColumn("run_id", "str"),
    ResultsColumn("ts_utc", "str"),
    ResultsColumn("git_sha", "str"),
    ResultsColumn("model", "str"),
    ResultsColumn("model_version", "str"),
    ResultsColumn("framework", "str"),
    ResultsColumn("defense_profile", "str"),
    ResultsColumn("scenario_id", "str"),
    ResultsColumn("task_id", "str"),
    ResultsColumn("template_id", "str"),
    ResultsColumn("seed", "int"),
    ResultsColumn("injected", "bool"),
    ResultsColumn("attack_success", "bool"),
    ResultsColumn("utility_success", "bool"),
    ResultsColumn("harm", "bool"),
    ResultsColumn("utv_usd", "float"),
    ResultsColumn("leaked_canaries", "int"),
    ResultsColumn("hitl_prompts", "int"),
    ResultsColumn("hitl_approved", "int"),
    ResultsColumn("detected", "bool"),
    ResultsColumn("tokens_in", "int"),
    ResultsColumn("tokens_out", "int"),
    ResultsColumn("cost_usd", "float"),
    ResultsColumn("latency_s", "float"),
    ResultsColumn("tool_calls", "int"),
    ResultsColumn("error", "str"),
)

RESULTS_COLUMN_NAMES: tuple[str, ...] = tuple(c.name for c in RESULTS_COLUMNS)
