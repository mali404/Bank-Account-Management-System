"""Re-check SPEC §12 baseline membership against the vendored OSCAL profiles.

The JSON files under ``controls/oscal/`` are the NIST SP 800-53 Rev.5
Release 5.2.0 LOW, MODERATE, and HIGH baseline profiles (public domain).
A control whose ``baseline`` list is empty is tailored in and must be
absent from all three profiles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    "low": "NIST_SP-800-53_rev5_LOW-baseline_profile.json",
    "moderate": "NIST_SP-800-53_rev5_MODERATE-baseline_profile.json",
    "high": "NIST_SP-800-53_rev5_HIGH-baseline_profile.json",
}


def oscal_id(control_id: str) -> str:
    """Map ``AC-2(4)`` to the OSCAL id ``ac-2.4``."""
    text = control_id.strip().lower()
    if "(" not in text:
        return text
    base, rest = text.split("(", 1)
    return f"{base}.{rest[:-1]}"


def profile_ids(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    included = data["profile"]["imports"][0]["include-controls"][0]["with-ids"]
    assert isinstance(included, list)
    return {str(item) for item in included}


def main() -> int:
    controls_path = ROOT / "controls" / "controls.yaml"
    raw = yaml.safe_load(controls_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    controls = raw["controls"]
    assert isinstance(controls, list) and controls, "controls.yaml has no controls"
    selected = {
        name: profile_ids(ROOT / "controls" / "oscal" / filename)
        for name, filename in PROFILES.items()
    }
    problems: list[str] = []
    for entry in controls:
        assert isinstance(entry, dict)
        control_id = str(entry["id"])
        claimed = entry.get("baseline") or []
        assert isinstance(claimed, list)
        oid = oscal_id(control_id)
        for name in PROFILES:
            present = oid in selected[name]
            if present != (name in claimed):
                problems.append(f"{control_id}: {name} claimed={name in claimed} oscal={present}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"controls-check: {len(controls)} controls match OSCAL SP 800-53 rev5 5.2.0 baselines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
