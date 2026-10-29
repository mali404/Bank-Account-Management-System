#!/usr/bin/env bash
# Export the step-ca root certificate out of the running container for later
# mTLS clients (bank <-> switch, bank-a PSP channel; SPEC §12 IA-3/SC-8, M2/M3).
#
# Writes the PEM to the git-ignored deploy/pki/out/root_ca.crt and prints its
# SHA-256 fingerprint. Idempotent: it overwrites the output each run. Requires
# the stack to be running (`make up`). No private keys ever leave the container.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${repo_root}"

out_dir="deploy/pki/out"
out_file="${out_dir}/root_ca.crt"
container_root="/home/step/certs/root_ca.crt"

compose=(docker compose --project-name "${AGENTBANK_PROJECT:-agentbank}" --env-file .env -f deploy/compose.yaml)

mkdir -p "${out_dir}"

# Copy the PEM out via the compose service (works regardless of host exposure).
"${compose[@]}" exec -T step-ca cat "${container_root}" > "${out_file}"

if ! grep -q "BEGIN CERTIFICATE" "${out_file}"; then
  echo "ERROR: ${out_file} does not look like a PEM certificate" >&2
  exit 1
fi

fingerprint="$("${compose[@]}" exec -T step-ca step certificate fingerprint "${container_root}")"

echo "Exported step-ca root certificate to ${out_file}"
echo "SHA-256 fingerprint: ${fingerprint}"
