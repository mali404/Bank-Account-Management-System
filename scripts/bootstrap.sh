#!/usr/bin/env bash
# Bootstrap the AgentBank-Sec testbed on a clean machine (SPEC §15, §18 M0).
#
# Idempotent. Steps:
#   1. check prerequisites (docker, docker compose v2, uv)
#   2. create .env from .env.example with freshly generated random passwords
#      (never overwrites an existing .env); this includes the step-ca init
#      password (the CA initialises itself inside its container on first start)
#   3. install the Python workspace (uv sync)
#   4. pull the compose images
#
# Set SKIP_DOCKER=1 to skip all docker steps (used by the CI lint job and on
# machines without docker).
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "${repo_root}"

SKIP_DOCKER="${SKIP_DOCKER:-0}"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; }

# --- 1. prerequisites ------------------------------------------------------
log "Checking prerequisites"
missing=0

if ! command -v uv >/dev/null 2>&1; then
  err "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
  missing=1
fi

if [[ "${SKIP_DOCKER}" != "1" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    err "docker not found. Install Docker Engine, or re-run with SKIP_DOCKER=1."
    missing=1
  elif ! docker compose version >/dev/null 2>&1; then
    err "docker compose v2 not found (need the 'docker compose' plugin)."
    missing=1
  fi
else
  log "SKIP_DOCKER=1 — skipping docker prerequisite checks"
fi

if [[ "${missing}" -ne 0 ]]; then
  err "Missing prerequisites; aborting."
  exit 1
fi

# --- 2. .env ---------------------------------------------------------------
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 24 | tr -d '\n/+=' | cut -c1-24
  else
    python3 -c "import secrets; print(secrets.token_urlsafe(18))"
  fi
}

if [[ -f .env ]]; then
  log ".env already exists — leaving it untouched"
else
  log "Creating .env from .env.example with generated passwords"
  cp .env.example .env
  pg_pw="$(gen_secret)"
  kc_pw="$(gen_secret)"
  stepca_pw="$(gen_secret)"
  # Portable in-place edit (GNU/BSD sed differ on -i).
  tmp="$(mktemp)"
  sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${pg_pw}|" \
      -e "s|^KC_BOOTSTRAP_ADMIN_PASSWORD=.*|KC_BOOTSTRAP_ADMIN_PASSWORD=${kc_pw}|" \
      -e "s|^STEPCA_INIT_PASSWORD=.*|STEPCA_INIT_PASSWORD=${stepca_pw}|" \
      .env > "${tmp}" && mv "${tmp}" .env
  chmod 600 .env
fi

# --- 3. Python workspace ---------------------------------------------------
log "Installing Python workspace with uv"
if [[ -f uv.lock ]]; then
  uv sync --all-packages --frozen
else
  uv sync --all-packages
fi

# --- 4. pull images --------------------------------------------------------
if [[ "${SKIP_DOCKER}" != "1" ]]; then
  log "Pulling compose images"
  docker compose --project-name agentbank --env-file .env -f deploy/compose.yaml pull
else
  log "SKIP_DOCKER=1 — skipping image pull"
fi

log "Bootstrap complete."
