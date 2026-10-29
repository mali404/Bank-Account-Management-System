"""Restore ``data/state`` from its snapshot. Exits non-zero if that takes 30s or more."""

from __future__ import annotations

import sys
from pathlib import Path

from agentbank_ledger.world import restore_tree


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/state")
    elapsed = restore_tree(root)
    print(f"reset in {elapsed:.3f}s")
    if elapsed >= 30:
        sys.exit(1)


if __name__ == "__main__":
    main()
