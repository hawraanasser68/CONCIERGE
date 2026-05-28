# Concierge — Runbook

**Owner:** Owner A  
**Last updated:** 2026-05-26

---

## 1. Run Locally

### Prerequisites

- Docker Desktop running
- `gh` CLI installed and authenticated (for PR workflows)
- No other service occupying ports 5432, 6379, 8200, 9000, 8000, 8001, 8002, 3000, 8501

### First-time setup

```bash
# 1. Copy env file and fill in any missing values
cp .env.example .env

# 2. Start everything
docker compose up --build

# The startup order is automatic:
#   vault → vault-init (seeds all secrets) → db → redis → backend → modelserver → guardrails → admin → widget
#
# Wait until you see:
#   backend    | startup_complete
#   widget     | ready on port 3000
```

### Verify the stack is healthy

```bash
# All services should show "healthy"
docker compose ps

# Backend health check
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# Login with the seeded platform manager
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=platform@concierge.test&password=devpassword"
# Expected: {"access_token": "...", "token_type": "bearer"}
```

### Re-seed dev data (after a DB wipe)

```bash
docker compose exec backend \
  python scripts/seed_dev_data.py
```

---

## 2. Run Tests

```bash
# Start only the DB and Redis (tests don't need Vault, modelserver, or guardrails)
docker compose up -d db redis

# Set the test DB URL and run the suite
TEST_DATABASE_URL=postgresql+asyncpg://concierge:concierge@localhost:5432/concierge_test \
  docker compose exec backend pytest
```

To run a specific test file:

```bash
docker compose exec backend pytest tests/integration/test_rls.py -v
```

---

## 3. Run Database Migrations

Migrations run automatically at container startup (`alembic upgrade head` in the Dockerfile CMD). To run manually:

```bash
docker compose exec backend alembic upgrade head
```

To check current migration state:

```bash
docker compose exec backend alembic current
```

**Only Owner A generates new migration files:**

```bash
docker compose exec backend alembic revision --autogenerate -m "describe the change"
```

Other owners define SQLAlchemy models and open a PR — Owner A generates and commits the migration file.

---

## 4. Rotate Secrets

All secrets live in Vault. The backend reads them at startup. Rotating a secret requires:

1. Write the new value to Vault
2. Rolling-restart the backend (old instances finish in-flight requests, new instances pick up the new secret)

### Rotate the widget signing key

```bash
# Generate a new 32-byte hex key
NEW_KEY=$(openssl rand -hex 32)

# Write to Vault
docker compose exec vault \
  vault kv put secret/widget/signing_key key="$NEW_KEY"

# Restart backend (all existing widget JWTs are immediately invalidated)
docker compose restart backend
```

> **Warning:** Rotating the widget signing key invalidates all active widget sessions immediately. Widget visitors will need to refresh their page to get a new token.

### Rotate the admin JWT signing key

The admin JWT uses the same key as the widget signing key (`app.state.widget_signing_key`). Rotating it invalidates all admin sessions — users will need to log in again.

### Rotate modelserver / guardrails tokens

```bash
NEW_TOKEN=$(openssl rand -hex 32)

docker compose exec vault \
  vault kv put secret/svc/modelserver token="$NEW_TOKEN"

# Restart both services that use this token
docker compose restart backend modelserver
```

---

## 5. Erase a Tenant (GDPR / CCPA)

### Via the API (normal path)

```bash
# Get a manager JWT first
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=platform@concierge.test&password=devpassword" \
  | jq -r .access_token)

# Erase the tenant
curl -s -X DELETE http://localhost:8000/api/v1/platform/tenants/<tenant_id> \
  -H "Authorization: Bearer $TOKEN"
# Expected: 204 No Content
```

### Via the CLI (manual / emergency path)

```bash
docker compose exec backend \
  python scripts/erase_tenant.py <tenant_id> --actor-id <operator_uuid>
```

The CLI calls the same `erase_tenant()` function as the API route, so the audit trail and Redis flush are identical.

### What erasure does

1. Sets `tenant.status = 'erasing'` — a second concurrent call gets 409
2. Deletes all tenant data in FK-safe order: `chunks → leads → escalations → cms_pages → agent_config → widgets → tenant_costs → users`
3. Sets `tenant.status = 'erased'` and `tenant.erased_at = now()`
4. Writes `tenant.erase_complete` to `audit_log`
5. Flushes all Redis keys under `conversation:{tenant_id}:*` and `ratelimit:{tenant_id}:*`

`audit_log` rows for erased tenants are **never deleted** — they are the compliance trail.

---

## 6. Suspend / Unsuspend a Tenant

Suspending a tenant instantly denies all existing JWTs for that tenant's users — no token revocation list needed. `get_current_tenant_id` checks `tenant.status == 'active'` on every request.

```bash
# Suspend (no API endpoint yet — run directly in the DB for now)
docker compose exec db psql -U concierge -d concierge \
  -c "UPDATE tenants SET status='suspended' WHERE id='<tenant_id>';"

# Unsuspend
docker compose exec db psql -U concierge -d concierge \
  -c "UPDATE tenants SET status='active' WHERE id='<tenant_id>';"
```

---

## 7. Tag a Release

```bash
# Ensure main is clean and all tests pass
git checkout main && git pull origin main
docker compose exec backend pytest

# Tag
git tag -a v0.1.0-week8 -m "Week 8 AIE demo release"
git push origin v0.1.0-week8
```

---

## 8. Common Troubleshooting

### Backend fails to start: "Vault authentication failed"

Vault is not ready or `vault-init` hasn't finished seeding secrets yet. Check:

```bash
docker compose logs vault-init
docker compose logs vault
```

If `vault-init` exited with an error, re-run it:

```bash
docker compose run --rm vault-init
```

### Backend fails to start: "RuntimeError: DATABASE_URL is not set"

The `DATABASE_URL` env var is missing. Check your `.env` file matches `.env.example`.

### Migrations fail: "relation already exists"

The DB already has tables from a previous run. Either:

```bash
# Option A: upgrade from current state
docker compose exec backend alembic upgrade head

# Option B: wipe and start fresh (destroys all data)
docker compose down -v && docker compose up --build
```

### RLS blocks a query unexpectedly

Check that `get_current_tenant_id` is in the route's dependency chain. If a route calls a repo directly without going through `get_current_tenant_id`, the `app.tenant_id` session variable is never set and RLS will block everything.

For the `tenant_manager` role, `set_manager_rls` sets the sentinel `'00000000-0000-0000-0000-000000000000'` — this intentionally matches no content rows. Manager routes must query `tenants` and `audit_log` only (neither has RLS).

### Widget token exchange returns 403: "Origin not allowed"

The request `Origin` header is not in `widget.allowed_origins`. Add it via the admin UI or:

```bash
curl -s -X PUT http://localhost:8000/api/v1/admin/widgets/<widget_id> \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allowed_origins": ["https://your-site.com"]}'
```
