# controls

NIST SP 800-53 Rev.5 mapping (SPEC §12).

M0 ships placeholders only:

- `controls.yaml` — machine-readable control → component/evidence map (`controls: []`).
- `audit_events.yaml` — the AU-2 audit-event catalog (`events: []`).

Deferred to **milestone M7**:

- `check_baselines.py` — re-verifies baseline membership from the NIST OSCAL
  content in CI (omitted until M7).
- the control evidence tests in `tests/controls/`.

The authoritative control table lives in SPEC §12.
