#!/usr/bin/env bash
# Regenerate the xsdata dataclass bindings for the SPEC §6.1 ISO 20022 message
# set from the fetched XSDs in iso20022/xsd/ (not committed; see iso20022/README.md).
#
# The generation is deterministic: a pinned xsdata version, one isolated
# subpackage per message (agentbank_iso.gen.<msg>), and a defensive header strip
# so no code-generator banner leaks into the tree. Run via `make iso-gen`.
set -euo pipefail

XSDATA_VERSION="26.10"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XSD_DIR="${REPO_ROOT}/iso20022/xsd"
SRC_DIR="${REPO_ROOT}/libs/agentbank_iso/src"
GEN_DIR="${SRC_DIR}/agentbank_iso/gen"

# message file stem -> binding subpackage name (SPEC §6.1 message set).
MESSAGES=(
  "head.001.001.02:head001_001_02"
  "pacs.008.001.08:pacs008_001_08"
  "pacs.002.001.10:pacs002_001_10"
  "pacs.004.001.10:pacs004_001_10"
  "camt.056.001.08:camt056_001_08"
  "camt.029.001.09:camt029_001_09"
  "pacs.028.001.03:pacs028_001_03"
  "pain.013.001.07:pain013_001_07"
  "pain.014.001.07:pain014_001_07"
  "pain.001.001.09:pain001_001_09"
  "pain.002.001.10:pain002_001_10"
  "camt.053.001.08:camt053_001_08"
  "camt.054.001.08:camt054_001_08"
  "camt.052.001.08:camt052_001_08"
  "admi.002.001.01:admi002_001_01"
)

echo "Regenerating ISO 20022 bindings with xsdata==${XSDATA_VERSION}"

# xsdata is pinned to XSDATA_VERSION in the dev dependency group / uv.lock, so the
# project environment is the reproducible source of the generator.
XSDATA=(uv run --project "${REPO_ROOT}" xsdata)

installed="$("${XSDATA[@]}" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1 || true)"
if [[ "${installed}" != "${XSDATA_VERSION}" ]]; then
  echo "error: expected xsdata ${XSDATA_VERSION}, found '${installed}'. Run 'uv sync --all-packages'." >&2
  exit 1
fi

for entry in "${MESSAGES[@]}"; do
  stem="${entry%%:*}"
  if [[ ! -f "${XSD_DIR}/${stem}.xsd" ]]; then
    echo "error: ${XSD_DIR}/${stem}.xsd missing. Run 'make xsd-fetch' first." >&2
    exit 1
  fi
done

# Generate every message in its own scratch directory: running xsdata repeatedly
# inside the package tree makes later runs pick up earlier output.
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

for entry in "${MESSAGES[@]}"; do
  stem="${entry%%:*}"
  pkg="${entry##*:}"
  echo "  ${stem}.xsd -> agentbank_iso.gen.${pkg}"
  mkdir -p "${work}/${pkg}"
  (cd "${work}/${pkg}" && "${XSDATA[@]}" generate "${XSD_DIR}/${stem}.xsd" \
    --package "agentbank_iso.gen.${pkg}" >/dev/null)
done

rm -rf "${GEN_DIR}"
mkdir -p "${GEN_DIR}"
for entry in "${MESSAGES[@]}"; do
  pkg="${entry##*:}"
  cp -R "${work}/${pkg}/agentbank_iso/gen/${pkg}" "${GEN_DIR}/${pkg}"
done

# Defensive: strip any code-generator banner comment some xsdata build might emit
# as the first line(s), so the committed sources read as hand-maintained.
python3 - "${GEN_DIR}" <<'PY'
import pathlib
import sys

gen = pathlib.Path(sys.argv[1])
for path in gen.rglob("*.py"):
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = False
    while lines and lines[0].lstrip().startswith("#"):
        banner = lines[0].lower()
        if any(tok in banner for tok in ("generated", "do not edit", "xsdata")):
            lines.pop(0)
            changed = True
        else:
            break
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
PY

# A marker package docstring so the tree documents itself (no tool name).
cat > "${GEN_DIR}/__init__.py" <<'PY'
"""Generated xsdata dataclass bindings for the SPEC §6.1 ISO 20022 messages.

Do not edit by hand. Regenerate with ``make iso-gen`` (``scripts/gen_iso_bindings.sh``)
from the committed XSDs in ``iso20022/xsd/``. One subpackage per message, named
after the message identifier (e.g. ``pacs008_001_08``).
"""
PY

echo "Done. Bindings written to ${GEN_DIR}."
