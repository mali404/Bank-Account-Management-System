#!/usr/bin/env bash
# Print the health of each core compose service and fail if any is not healthy
# (SPEC §15, §18 M0). Used by `make health` and after `make up`.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "${repo_root}"

compose=(docker compose --project-name agentbank --env-file .env -f deploy/compose.yaml)

services=(postgres nats keycloak step-ca)
rc=0

printf '%-12s %s\n' "SERVICE" "HEALTH"
for svc in "${services[@]}"; do
  cid="$("${compose[@]}" ps -q "${svc}" 2>/dev/null || true)"
  if [[ -z "${cid}" ]]; then
    status="not running"
  else
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${cid}" 2>/dev/null || echo unknown)"
  fi
  printf '%-12s %s\n' "${svc}" "${status}"
  if [[ "${status}" != "healthy" ]]; then
    rc=1
  fi
done

if [[ "${rc}" -ne 0 ]]; then
  echo "One or more services are not healthy." >&2
fi
exit "${rc}"
