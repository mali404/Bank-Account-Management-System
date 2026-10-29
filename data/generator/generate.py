"""Write a seeded world to ``data/state`` and ``data/manifest.json``.

``make seed`` runs this. The same ``--seed`` produces the same canonical
digest. The snapshot next to the state files is what ``make reset`` restores.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentbank_ledger.seed import seed_world
from agentbank_ledger.world import World


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the three banks and the switch.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/state"))
    args = parser.parse_args()
    world = World.create(args.out)
    manifest = seed_world(world, args.seed)
    world.mark_snapshot()
    manifest_path = args.out.parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "sha256": manifest["canonical_sha256"]}))


if __name__ == "__main__":
    main()
