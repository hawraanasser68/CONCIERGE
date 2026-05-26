# Owner A — vault/policies/api.hcl
#
# Vault policy for the concierge-api service account.
# Grants read-only access to exactly the secrets the backend needs at startup.
# No write access, no access to other paths, no ability to manage Vault itself.
#
# In dev mode (root token) this policy is not enforced, but it documents
# the principle of least privilege for production deployments.

# Service tokens — backend sends these when calling modelserver and guardrails
path "secret/data/svc/*" {
  capabilities = ["read"]
}

# Widget JWT signing key — used by sign_widget_jwt() and verify_widget_jwt()
path "secret/data/widget/signing_key" {
  capabilities = ["read"]
}

# Database password
path "secret/data/db/password" {
  capabilities = ["read"]
}

# LLM API key — Anthropic key, empty on Day 1
path "secret/data/llm/api_key" {
  capabilities = ["read"]
}

# Embedding API key — empty on Day 1
path "secret/data/embed/api_key" {
  capabilities = ["read"]
}

# MinIO credentials — used by the tenant erasure background task
path "secret/data/minio/*" {
  capabilities = ["read"]
}
