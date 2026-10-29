#!/usr/bin/env python3
"""Verify or re-fetch the ISO 20022 XSDs against iso20022/xsd/MANIFEST.yaml.

Standard library only (no PyYAML): the manifest uses a fixed, simple shape — a
top-level ``messages:`` list of ``key: value`` mappings — which a small parser
below reads directly.

The XSDs are not committed: ``install`` downloads them from the official
iso20022.org catalogue into iso20022/xsd/ and only writes a file whose SHA-256
matches the manifest.

Usage:
    python scripts/fetch_xsd.py install  # download missing/mismatched XSDs (verified)
    python scripts/fetch_xsd.py verify   # offline: recompute SHA-256 vs manifest
    python scripts/fetch_xsd.py fetch    # re-download from source_url, compare only
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
XSD_DIR = REPO_ROOT / "iso20022" / "xsd"
MANIFEST = XSD_DIR / "MANIFEST.yaml"


def parse_manifest(text: str) -> list[dict[str, str]]:
    """Parse the fixed ``messages:`` list-of-mappings manifest shape."""
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_messages = False
    for raw in text.splitlines():
        # Manifest values never contain '#', so comment stripping is unambiguous.
        stripped = raw.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped == "messages:":
            in_messages = True
            continue
        if not in_messages:
            continue
        if stripped.startswith("- "):
            current = {}
            entries.append(current)
            stripped = stripped[2:].strip()
        if current is None:
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            current[key.strip()] = _unquote(value.strip())
    return entries


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_entries() -> list[dict[str, str]]:
    entries = parse_manifest(MANIFEST.read_text(encoding="utf-8"))
    if not entries:
        raise SystemExit("manifest has no message entries")
    return entries


def verify() -> int:
    failures = 0
    for entry in load_entries():
        path = XSD_DIR / entry["file"]
        if not path.exists():
            print(f"MISSING  {entry['file']}")
            failures += 1
            continue
        actual = sha256_of(path)
        if actual != entry["sha256"]:
            print(f"MISMATCH {entry['file']}\n  manifest {entry['sha256']}\n  actual   {actual}")
            failures += 1
        else:
            print(f"OK       {entry['file']}")
    if failures:
        print(f"\n{failures} file(s) failed verification")
        return 1
    print(f"\nall {len(load_entries())} XSD hashes match the manifest")
    return 0


def fetch() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for entry in load_entries():
            url = entry["source_url"]
            dest = tmp_dir / entry["file"]
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    dest.write_bytes(resp.read())
            except Exception as exc:  # network/HTTP errors
                print(f"ERROR    {entry['file']}: {exc}")
                failures += 1
                continue
            actual = sha256_of(dest)
            if actual != entry["sha256"]:
                print(
                    f"MISMATCH {entry['file']}\n  manifest {entry['sha256']}\n  upstream {actual}"
                )
                failures += 1
            else:
                print(f"OK       {entry['file']}")
    if failures:
        print(f"\n{failures} file(s) differ from or could not be fetched from upstream")
        return 1
    print("\nall upstream hashes match the manifest")
    return 0


def install() -> int:
    failures = 0
    for entry in load_entries():
        path = XSD_DIR / entry["file"]
        if path.exists() and sha256_of(path) == entry["sha256"]:
            print(f"PRESENT  {entry['file']}")
            continue
        try:
            with urllib.request.urlopen(entry["source_url"], timeout=60) as resp:
                data = resp.read()
        except Exception as exc:  # network/HTTP errors
            print(f"ERROR    {entry['file']}: {exc}")
            failures += 1
            continue
        actual = hashlib.sha256(data).hexdigest()
        if actual != entry["sha256"]:
            print(f"MISMATCH {entry['file']}\n  manifest {entry['sha256']}\n  upstream {actual}")
            failures += 1
            continue
        tmp = path.with_suffix(".xsd.part")
        tmp.write_bytes(data)
        tmp.replace(path)
        print(f"FETCHED  {entry['file']}")
    if failures:
        print(f"\n{failures} file(s) could not be installed")
        return 1
    print("\nall XSDs present and verified")
    return 0


def main(argv: list[str]) -> int:
    commands = {"install": install, "verify": verify, "fetch": fetch}
    if len(argv) != 2 or argv[1] not in commands:
        print(__doc__)
        return 2
    return commands[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
