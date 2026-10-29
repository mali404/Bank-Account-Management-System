"""`python -m bankbench` writes a mock-model run under ``results/``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .fp import false_positive_rates
from .report import write_run
from .runner import run_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bankbench with the mock model.")
    parser.add_argument("--model", default="mock-local")
    parser.add_argument("--defense", default="D0", help="Comma-separated defense profiles.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    defenses = tuple(part.strip() for part in str(args.defense).split(",") if part.strip())
    rows = run_catalog(seed=args.seed, model=str(args.model), defenses=defenses)
    directory = args.out or Path("results") / f"mock-{args.seed}-{'-'.join(defenses)}"
    rates = false_positive_rates(defenses)
    report = write_run(rows, directory, rates)
    print(report)


if __name__ == "__main__":
    main()
