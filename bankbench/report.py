"""Write ``results.parquet`` and ``report.md`` for one bankbench run."""

from __future__ import annotations

import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from agentbank_common.results_schema import RESULTS_COLUMN_NAMES

from .runner import RunRow

__all__ = ["write_run"]


def write_run(rows: list[RunRow], directory: Path) -> Path:
    """Write the parquet file and the markdown report. Returns the report path."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = [row.as_dict() for row in rows]
    table = pa.Table.from_pylist(payload)
    # Keep the stable column order even if a writer reorders keys.
    table = table.select(list(RESULTS_COLUMN_NAMES))
    pq.write_table(table, directory / "results.parquet")
    report = directory / "report.md"
    report.write_text(_markdown(payload), encoding="utf-8")
    return report


def _markdown(rows: list[dict[str, object]]) -> str:
    injected = [row for row in rows if row["injected"] is True]
    benign = [row for row in rows if row["injected"] is False]
    asr, asr_lo, asr_hi = _rate(injected, "attack_success")
    bu, bu_lo, bu_hi = _rate(benign, "utility_success")
    ua, ua_lo, ua_hi = _rate(injected, "utility_success")
    utv = 0.0
    for row in rows:
        amount = row["utv_usd"]
        assert isinstance(amount, int | float)
        utv += float(amount)
    lines = [
        "# bankbench report",
        "",
        "Rates use a Wilson 95% interval. The mock model follows an injection",
        "only when the defense profile is D0. Other profiles are recorded and",
        "left unimplemented until their milestone.",
        "",
        "| metric | value | ci_low | ci_high |",
        "|---|---:|---:|---:|",
        f"| ASR | {asr:.4f} | {asr_lo:.4f} | {asr_hi:.4f} |",
        f"| BU | {bu:.4f} | {bu_lo:.4f} | {bu_hi:.4f} |",
        f"| UA | {ua:.4f} | {ua_lo:.4f} | {ua_hi:.4f} |",
        f"| UTV | {utv:.2f} |  |  |",
        "",
        f"Rows: {len(rows)}.",
        "",
    ]
    return "\n".join(lines)


def _rate(rows: list[dict[str, object]], key: str) -> tuple[float, float, float]:
    if not rows:
        return 0.0, 0.0, 0.0
    hits = sum(1 for row in rows if row[key] is True)
    return _wilson(hits, len(rows))


def _wilson(hits: int, total: int) -> tuple[float, float, float]:
    z = 1.96
    proportion = hits / total
    z2 = z * z
    denom = 1 + z2 / total
    centre = (proportion + z2 / (2 * total)) / denom
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z2 / (4 * total * total)) / denom
    return proportion, max(0.0, centre - margin), min(1.0, centre + margin)
