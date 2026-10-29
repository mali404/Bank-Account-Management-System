# controls

NIST SP 800-53 Rev.5 mapping (SPEC §12).

- `controls.yaml` lists each control, its baseline, the implementation in this
  testbed, and the evidence test.
- `audit_events.yaml` is the AU-2 catalog.
- `check_baselines.py` checks baseline membership against the OSCAL profiles
  in `oscal/`. `make controls-check` runs it.
- `playbook.md` is the IR-4 freeze / recall / revoke note.

Evidence tests live in `tests/controls/`.
