"""The XSD MANIFEST covers exactly the §6.1 set and all hashes match."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from agentbank_iso.messages import all_message_ids, xsd_dir

MANIFEST = xsd_dir() / "MANIFEST.yaml"
_ENTRIES = yaml.safe_load(MANIFEST.read_text())["messages"]


def test_manifest_covers_exactly_the_6_1_set() -> None:
    manifest_ids = {e["message"] for e in _ENTRIES}
    assert manifest_ids == set(all_message_ids())
    assert len(_ENTRIES) == len(all_message_ids())


def test_manifest_entries_have_required_keys() -> None:
    required = {"message", "version", "file", "sha256", "source_url", "area", "used_for"}
    for entry in _ENTRIES:
        assert required <= set(entry), entry["message"]
        assert entry["source_url"].startswith("https://www.iso20022.org/")


def test_manifest_hashes_match_committed_files() -> None:
    for entry in _ENTRIES:
        path = Path(xsd_dir()) / entry["file"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == entry["sha256"], entry["file"]


def test_verify_notes_present_for_unverified_versions() -> None:
    notes = {e["message"]: e.get("notes") for e in _ENTRIES}
    for mid in ("head.001.001.02", "pain.013.001.07", "pain.014.001.07"):
        assert notes[mid] and "[VERIFY]" in notes[mid]
