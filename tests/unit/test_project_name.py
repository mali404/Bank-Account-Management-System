"""The compose project name must stay configurable via ``AGENTBANK_PROJECT``.

No file outside ``docs/`` may hard-code the ``--project-name`` flag with a
literal ``agentbank`` value: every real invocation has to go through the
``AGENTBANK_PROJECT`` variable (with ``agentbank`` as the default) so several
checkouts can coexist on one host.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Built from parts so this test file is not itself an offender.
LITERAL = "--project-name" + " agentbank"


def test_project_name_not_hardcoded_outside_docs(repo_root: Path) -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    offenders: list[str] = []
    for rel in tracked:
        if rel.startswith("docs/"):
            continue
        path = repo_root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if LITERAL in text:
            offenders.append(rel)

    assert not offenders, f"{LITERAL!r} is hard-coded in: {offenders}"
