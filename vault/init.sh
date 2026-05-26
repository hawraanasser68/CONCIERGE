#!/bin/sh
# Owner A — vault/init.sh
#
# Runs once inside the vault-init container after Vault is healthy.
# Seeds all 8 secret paths. The backend reads these at startup;
# a missing required secret causes startup failure (fail fast, fail loud).
#
# Vault is in dev mode: root token = "root", KV v2 is pre-mounted at secret/.
# This script is idempotent — safe to run multiple times.

set -e

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-root}"

export VAULT_ADDR VAULT_TOKEN

echo "[vault-init] Waiting for Vault to be ready..."
until vault status > /dev/null 2>&1; do
  sleep 1
done
echo "[vault-init] Vault is ready."

# Enable KV v2 at secret/ if not already enabled.
# In dev mode it's pre-enabled; this makes the script safe in prod-like setups too.
vault secrets enable -version=2 -path=secret kv 2>/dev/null || true

# ── Service tokens ────────────────────────────────────────────────────────────
# Random 32-byte hex tokens. Owner C's modelserver and guardrails read these
# to validate that inbound calls come from the backend, not from the internet.

MODELSERVER_TOKEN=$(head -c 32 /dev/urandom | xxd -p)
GUARDRAILS_TOKEN=$(head -c 32 /dev/urandom | xxd -p)

vault kv put secret/svc/modelserver token="${MODELSERVER_TOKEN}"
echo "[vault-init] secret/svc/modelserver seeded."

vault kv put secret/svc/guardrails token="${GUARDRAILS_TOKEN}"
echo "[vault-init] secret/svc/guardrails seeded."

# ── Widget signing key ────────────────────────────────────────────────────────
# HS256 secret for signing per-widget JWTs (1h TTL).
# Owner D's loader POSTs to /api/v1/widget/token; this key signs the response.

WIDGET_SIGNING_KEY=$(head -c 32 /dev/urandom | xxd -p)
vault kv put secret/widget/signing_key key="${WIDGET_SIGNING_KEY}"
echo "[vault-init] secret/widget/signing_key seeded."

# ── Database password ─────────────────────────────────────────────────────────
# Mirrors POSTGRES_PASSWORD from the environment so the backend fetches it
# from Vault rather than reading raw env vars directly.

vault kv put secret/db/password password="${POSTGRES_PASSWORD}"
echo "[vault-init] secret/db/password seeded."

# ── LLM and embedding API keys ────────────────────────────────────────────────
# Left empty on Day 1 — team fills these before any LLM call is made.
# Backend logs a warning if these are empty but does not crash on startup.

vault kv put secret/llm/api_key key=""
echo "[vault-init] secret/llm/api_key seeded (empty — fill before LLM calls)."

vault kv put secret/embed/api_key key=""
echo "[vault-init] secret/embed/api_key seeded (empty — fill before embed calls)."

# ── MinIO credentials ─────────────────────────────────────────────────────────
# Dev defaults. Change before any real deployment.
# Used by the tenant erasure flow to flush objects under tenants/{tenant_id}/.

vault kv put secret/minio/access_key key="${MINIO_ROOT_USER:-minioadmin}"
vault kv put secret/minio/secret_key key="${MINIO_ROOT_PASSWORD:-minioadmin}"
echo "[vault-init] secret/minio/* seeded."

# ── Vault policy for the backend service account ──────────────────────────────
# Written now so it's ready for a non-dev Vault. In dev mode the root token
# already has full access, but the policy documents exactly what the backend needs.

vault policy write concierge-api /vault-config/policies/api.hcl
echo "[vault-init] concierge-api policy written."

echo "[vault-init] All 8 secret paths seeded successfully."
