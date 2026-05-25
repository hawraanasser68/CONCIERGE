# Owner A — Task List

Format: `[ID] [P?] Description — file`
`[P]` = can run in parallel with other `[P]` tasks in the same phase.

---

## Phase 0 — Infrastructure (Day 1, first block — no parallelism, strict order)

- [ ] A-001 Write `docker-compose.yml` with all 10 services (db, redis, vault, minio, jaeger, backend, modelserver, guardrails, admin, widget), healthchecks, and `depends_on` chains — `docker-compose.yml`
- [ ] A-002 Write `vault/init.sh` to seed all 8 secret paths on first `docker-compose up` — `vault/init.sh`, `vault/policies/api.hcl`
- [ ] A-003 Write `.env.example` documenting every required environment variable — `.env.example`
- [ ] A-004 Verify `docker compose up` brings all services to healthy (modelserver + guardrails use Owner C's Day-1 stubs)

---

## Phase 1 — Database Schema (Day 1, second block)

- [ ] A-005 Write all 10 SQLAlchemy models — `backend/app/models/base.py`, `tenant.py`, `user.py`, `widget.py`, `cms.py`, `chunk.py`, `lead.py`, `escalation.py`, `agent_config.py`, `audit_log.py`
- [ ] A-006 Configure Alembic — `backend/alembic.ini`, `backend/migrations/env.py`
- [ ] A-007 Generate and write initial migration with ALL tables + RLS policies + IVFFlat index — `backend/migrations/versions/0001_initial_schema.py`
- [ ] A-008 Add seeded tenants (aaaa..., bbbb...) and admin users to the migration or a data migration
- [ ] A-009 Run `alembic upgrade head` inside the running db container and confirm all tables exist with RLS active
- [ ] A-010 Write integration test: Tenant A session cannot see Tenant B rows — `backend/tests/integration/`

---

## Phase 2 — FastAPI Core (Day 1, third block)

- [ ] A-011 Write `backend/app/config.py` — pydantic-settings, `extra="forbid"`, reads all env vars — `backend/app/config.py`
- [ ] A-012 Write `backend/app/lifespan.py` — startup: DB engine, Redis pool, Vault client, httpx session; shutdown: close all — `backend/app/lifespan.py`
- [ ] A-013 Write `backend/app/main.py` — FastAPI app + pkgutil auto-discovery loop — `backend/app/main.py`
- [ ] A-014 Write `backend/app/logging_setup.py` — structlog + JSON output — `backend/app/logging_setup.py`
- [ ] A-015 Write `backend/app/tracing.py` stub — OpenTelemetry init, one no-op span (Owner C fills real spans) — `backend/app/tracing.py`

---

## Phase 3 — Auth & Tenancy (Day 1, fourth block — all parallel after A-013)

- [ ] A-016 [P] Write `backend/app/auth/roles.py` — `Role` enum, `require_role()` dependency — `backend/app/auth/roles.py`
- [ ] A-017 [P] Write `backend/app/auth/users.py` — fastapi-users config, User model integration — `backend/app/auth/users.py`
- [ ] A-018 [P] Write `backend/app/auth/widget_token.py` — `sign_widget_jwt()` and `verify_widget_jwt()` with 7-step validation chain — `backend/app/auth/widget_token.py`
- [ ] A-019 [P] Write `backend/app/auth/service_token.py` — Vault-sourced service token validator for inbound calls — `backend/app/auth/service_token.py`
- [ ] A-020 [P] Write `backend/app/tenancy/rls.py` — `set_tenant_rls()` using transaction-scoped `set_config` — `backend/app/tenancy/rls.py`
- [ ] A-021 [P] Write `backend/app/tenancy/repository.py` — `TenantRepository` base mixin with `scoped()` method — `backend/app/tenancy/repository.py`
- [ ] A-022 [P] Write `backend/app/tenancy/audit.py` — `write_audit_log()` async helper — `backend/app/tenancy/audit.py`
- [ ] A-023 [P] Write `backend/app/core/errors.py` — `ToolError`, HTTP exception helpers — `backend/app/core/errors.py`

---

## Phase 4 — Dependencies & Schemas (Day 1, fifth block)

- [ ] A-024 Write `backend/app/dependencies.py` — `get_session`, `get_current_user`, `get_current_tenant_id` (decode JWT → verify tenant active → set RLS → return UUID), `get_widget_session` — `backend/app/dependencies.py`
- [ ] A-025 [P] Write all Pydantic schemas — `backend/app/schemas/tenant.py`, `user.py`, `widget.py`, `chat.py`, `lead.py`, `cms.py`

---

## Phase 5 — Routes (Day 1, sixth block — all parallel)

- [ ] A-026 [P] Write `backend/app/routes/health.py` — `GET /health` returns `{"status": "ok"}` — `backend/app/routes/health.py`
- [ ] A-027 [P] Write `backend/app/routes/auth.py` — login, register, invite endpoints via fastapi-users — `backend/app/routes/auth.py`
- [ ] A-028 [P] Write `backend/app/routes/manager.py` — `POST /api/v1/platform/tenants` provisioning flow — `backend/app/routes/manager.py`
- [ ] A-029 [P] Write `backend/app/routes/tenant_admin.py` — widget CRUD, leads list, escalations list, agent-config get/put; all require `tenant_admin` role — `backend/app/routes/tenant_admin.py`
- [ ] A-030 [P] Write stub `backend/app/routes/cms.py` — all routes return HTTP 501 (B replaces this file) — `backend/app/routes/cms.py`
- [ ] A-031 [P] Write stub `backend/app/routes/chat.py` — returns HTTP 501 (B replaces) — `backend/app/routes/chat.py`
- [ ] A-032 [P] Write stub `backend/app/routes/widget.py` — returns HTTP 501 (D replaces) — `backend/app/routes/widget.py`

---

## Phase 6 — Services & Repositories (Day 2)

- [ ] A-033 [P] Write `backend/app/services/rate_limiter.py` — Redis-backed, 5 rate limit configs — `backend/app/services/rate_limiter.py`
- [ ] A-034 [P] Write `backend/app/services/cost_meter.py` — `record_llm_usage`, `record_embed_usage`, `record_classify_call` with upsert — `backend/app/services/cost_meter.py`
- [ ] A-035 [P] Write `backend/app/repositories/base.py` — re-exports `TenantRepository` — `backend/app/repositories/base.py`
- [ ] A-036 [P] Write `backend/app/repositories/tenant_repo.py` — `backend/app/repositories/tenant_repo.py`
- [ ] A-037 [P] Write `backend/app/repositories/user_repo.py` — `backend/app/repositories/user_repo.py`
- [ ] A-038 [P] Write `backend/app/repositories/widget_repo.py` — origin lookup for token exchange — `backend/app/repositories/widget_repo.py`
- [ ] A-039 [P] Write `backend/app/repositories/audit_log_repo.py` — append-only write — `backend/app/repositories/audit_log_repo.py`
- [ ] A-040 [P] Write `backend/app/repositories/agent_config_repo.py` — get/update per-tenant config (B also imports this) — `backend/app/repositories/agent_config_repo.py`
- [ ] A-041 [P] Write `backend/app/repositories/tenant_costs_repo.py` — daily upsert — `backend/app/repositories/tenant_costs_repo.py`
- [ ] A-042 [P] Write `backend/app/tenancy/manager.py` — full provisioning + erasure flows — `backend/app/tenancy/manager.py`

---

## Phase 7 — Scripts & Tests (Day 2-3)

- [ ] A-043 [P] Write `backend/scripts/seed_dev_data.py` — idempotent: seeds two tenants + admin users locally — `backend/scripts/seed_dev_data.py`
- [ ] A-044 [P] Write `backend/scripts/erase_tenant.py` — CLI wrapper for GDPR erasure flow — `backend/scripts/erase_tenant.py`
- [ ] A-045 [P] Write `backend/tests/conftest.py` — test settings, fake LLM stub, fake modelserver stub — `backend/tests/conftest.py`
- [ ] A-046 [P] Write unit tests for `get_current_tenant_id`: correct tenant ✓, wrong tenant → 403, spoofed body tenant_id ignored — `backend/tests/unit/`
- [ ] A-047 [P] Write integration test: RLS isolation (Tenant A cannot see Tenant B rows on same pool) — `backend/tests/integration/`
- [ ] A-048 Write `backend/pyproject.toml` with all deps — `backend/pyproject.toml`
- [ ] A-049 Write `backend/Dockerfile` — `backend/Dockerfile`
- [ ] A-050 Write `.pre-commit-config.yaml` — ruff + ruff-format — `.pre-commit-config.yaml`

---

## Phase 8 — Documentation (Day 3 / Demo Prep)

- [ ] A-051 Write `docs/DESIGN.md` — tenant isolation strategy, scaling story, role model, cost-per-tenant — `docs/DESIGN.md`
- [ ] A-052 Write `docs/RUNBOOK.md` — how to run locally, deploy, rotate secrets, erase a tenant, tag v0.1.0-week8 — `docs/RUNBOOK.md`

---

## Day 1 Completion Checklist (Gate — nothing else starts until all pass)

- [ ] `docker compose up` — all 10 services healthy
- [ ] Vault seeded with all 8 paths
- [ ] `GET /health` → 200
- [ ] `POST /api/v1/auth/login` → JWT
- [ ] `get_current_tenant_id` returns correct UUID; returns 403 for inactive tenant
- [ ] RLS isolation integration test green
- [ ] Two seeded tenants readable
- [ ] Vault service tokens readable by Owner C
- [ ] Stubs for cms.py, chat.py, widget.py committed (return 501)
