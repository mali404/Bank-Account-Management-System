"""LICENSE must be Apache-2.0 and NOTICE must name Munawar Ali."""

from __future__ import annotations

from pathlib import Path


def test_license_is_apache_2(repo_root: Path) -> None:
    text = (repo_root / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0" in text


def test_notice_names_copyright_holder(repo_root: Path) -> None:
    text = (repo_root / "NOTICE").read_text(encoding="utf-8")
    assert "Munawar Ali" in text
    assert "2026" in text
    # The NOTICE must make the simulated nature explicit.
    assert "simulated" in text.lower()


def test_citation_metadata(repo_root: Path) -> None:
    text = (repo_root / "CITATION.cff").read_text(encoding="utf-8")
    assert "cff-version: 1.2.0" in text
    assert "AgentBank-Sec Testbed" in text
    assert "Apache-2.0" in text
    assert "Ali" in text
