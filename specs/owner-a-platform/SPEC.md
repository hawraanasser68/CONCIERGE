# Owner A — Platform, Tenancy, Isolation & Provisioning

**Owner:** Owner A
**Day-1 deliverable deadline:** End of Day 1 — everyone is blocked until these items are done

---

## Scope

Owner A owns everything that makes multi-tenancy work and stay secure:

- `docker-compose.yml` — entirely, no exceptions
- The complete Postgres schema — ALL tables, defined in one initial Alembic migration on Day 1. No other owner ever runs `alembic revision`.
- Row-Level Security policies on all tenant-scoped tables
- `backend/app/main.py` — FastAPI app, lifespan, and route auto-discovery (written once on Day 1, nobody else touches it)
- Authentication via `fastapi-users`: login, registration, JWT issuance
- Three-role model: `tenant_manager`, `tenant_admin`, `member`
- `get_current_tenant_id` — the single source of tenant context for every request
- RLS session variable set and reset on every request
- Repository-layer scoping convention and enforcement in code review
- `backend/app/repositories/` — base repo + platform model repos (A writes); Owner B adds B-domain repos to this directory
- `backend/scripts/` — dev seed script and GDPR erasure CLI
- Tenant provisioning flow (create tenant, invite first admin)
- Tenant erasure flow (GDPR/CCPA right-to-erasure)
- Audit log
- Per-tenant rate limiting (Redis-backed) — `backend/app/services/rate_limiter.py`
- Per-tenant cost attribution — `backend/app/services/cost_meter.py`
- Vault setup and secret seeding
- `docs/DESIGN.md` — tenant isolation strategy, scaling story, cost-per-tenant, role model
- `docs/RUNBOOK.md` — operational guide: run locally, deploy, rotate secrets, erase tenant, tag release

Owner A does NOT own:
- Agent, RAG, memory, CMS content pipeline (Owner B)
- Classifier model, model server, guardrails sidecar (Owner C)
- React widget, admin Streamlit UI, CI/CD pipeline (Owner D)

---

## Files and Directories — What Owner A Writes

```
docker-compose.yml                    ← A owns entirely
.env.example                          ← A writes; documents every required var
.pre-commit-config.yaml               ← A sets up: ruff + ruff-format (no eslint — D handles that)
eval_thresholds.yaml                  ← A creates the file; D populates it Day 1

vault/
  init.sh                             ← seeds all Vault paths on docker-compose up
  policies/
    api.hcl                           ← Vault policy for the backend service account

backend/
  pyproject.toml                      ← A manages; others submit PRs to add deps
  uv.lock
  Dockerfile
  alembic.ini
  migrations/
    env.py                            ← A configures
    versions/
      0001_initial_schema.py          ← ALL tables — one migration, Day 1, never extended

  app/
    main.py                           ← A writes on Day 1, nobody else ever edits this
    config.py                         ← pydantic-settings; extra="forbid"; reads env/Vault
    lifespan.py                       ← startup: DB engine, Redis pool, Vault client, httpx session
    dependencies.py                   ← get_session, get_current_user, get_current_tenant_id,
                                         get_widget_session
    logging_setup.py                  ← structlog + JSON + file handler
    tracing.py                        ← OpenTelemetry wiring (stubs; Owner C fills real spans)

    auth/
      users.py                        ← fastapi-users config + User model integration
      roles.py                        ← TenantManager / TenantAdmin / Member enum + dependencies
      widget_token.py                 ← PyJWT sign/verify for per-widget tokens (D calls this)
      service_token.py                ← Vault-sourced service-to-service token validator

    tenancy/
      rls.py                          ← set_config('app.tenant_id', ..., TRUE) dependency
      repository.py                   ← base repo mixin: always filters by tenant_id
      manager.py                      ← Tenant Manager provision / suspend / erase logic
      audit.py                        ← audit_log writer

    routes/
      health.py                       ← GET /health
      auth.py                         ← POST /api/v1/auth/login, register, invite
      manager.py                      ← POST /api/v1/platform/tenants (provisioning)
      tenant_admin.py                 ← A owns entirely: /api/v1/admin/widgets (CRUD + toggle),
                                         /api/v1/admin/leads (paginated), /api/v1/admin/escalations,
                                         /api/v1/admin/agent-config; all require tenant_admin role
      # stubs for B and D on Day 1:
      cms.py                          ← stub returning 501 (B replaces entirely)
      chat.py                         ← stub returning 501 (B replaces entirely)
      widget.py                       ← stub returning 501 (D replaces entirely)

    models/
      base.py                         ← DeclarativeBase + TenantMixin (tenant_id column)
      tenant.py                       ← Tenant model
      user.py                         ← User model
      widget.py                       ← Widget model
      cms.py                          ← CmsPage model
      chunk.py                        ← Chunk model (pgvector column)
      lead.py                         ← Lead model
      escalation.py                   ← Escalation model
      agent_config.py                 ← AgentConfig model
      audit_log.py                    ← AuditLog model

    schemas/
      tenant.py
      user.py
      widget.py
      chat.py
      lead.py
      cms.py

    repositories/
      base.py                         ← re-exports TenantRepository mixin; all concrete repos import from here
      tenant_repo.py                  ← Tenant CRUD (no RLS — manager-scoped)
      user_repo.py                    ← User lookup by email, role checks
      widget_repo.py                  ← Widget CRUD, allowed_origins lookup
      audit_log_repo.py               ← append-only write; no delete path
      tenant_costs_repo.py            ← upsert daily cost rows
      agent_config_repo.py            ← get/update agent config per tenant (A needs it for provisioning seed;
                                         B imports and uses it in agent.py and cms routes)
      # B writes: chunk_repo.py, lead_repo.py, escalation_repo.py, cms_page_repo.py

    services/
      cost_meter.py                   ← per-tenant LLM/embed usage (Owner B calls this)
      rate_limiter.py                 ← per-tenant Redis rate limiting (Owner B calls this)

    core/
      errors.py                       ← ToolError + HTTPException helpers

  scripts/
    seed_dev_data.py                  ← idempotent: inserts two tenants + admin users if not present
    erase_tenant.py                   ← CLI wrapper around the erasure flow (for manual GDPR ops)

  tests/
    conftest.py                       ← test settings, fake LLM stub, fake modelserver stub
    unit/
    integration/
    e2e/

docs/
  DESIGN.md                           ← A writes: isolation strategy, scaling story, role model
  RUNBOOK.md                          ← A writes: how to run locally, deploy, rotate secrets,
                                         erase a tenant (GDPR flow), tag v0.1.0-week8 release
  DECISIONS.md                        ← B writes: agent-vs-workflow hybrid, chunking strategy,
                                         embedding choice, caching policy; C contributes classifier
                                         model choice section
  EVALS.md                            ← B + C co-write: what each CI gate measures, how to
                                         interpret scores, RAG judge agreement methodology
  SECURITY.md                         ← C writes: threat model, the security wall (injection,
                                         jailbreak, cross-tenant, PII), red-team methodology
```

Owner A does NOT write anything under:
- `backend/app/services/classifier_client.py`
- `backend/app/services/guardrails_client.py`
- `backend/app/services/llm_client.py`
- `backend/app/services/embeddings_client.py`
- `backend/app/services/rag.py`
- `backend/app/services/router.py`
- `backend/app/services/agent.py`
- `backend/app/services/redaction.py`
- `backend/app/tools/`
- `backend/evals/`
- `modelserver/`
- `guardrails/`
- `admin/`
- `widget/`

---

## Complete Database Schema (All Tables — Day 1)

Owner A defines every table in one Alembic migration. Other owners write SQLAlchemy models mapping to these tables; they never create migration files.

### Table: tenants

```sql
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'erasing', 'erased')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erased_at   TIMESTAMPTZ
);
```

No `tenant_id` column. No RLS. Access controlled by role checks at route level.

### Table: users

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID REFERENCES tenants(id) ON DELETE CASCADE,  -- NULL for tenant_manager
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL
                        CHECK (role IN ('tenant_manager', 'tenant_admin', 'member')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table: widgets

```sql
CREATE TABLE widgets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    allowed_origins TEXT[] NOT NULL DEFAULT '{}',
    greeting        TEXT NOT NULL DEFAULT 'Hi! How can I help you today?',
    persona_name    TEXT NOT NULL DEFAULT 'Assistant',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table: agent_config

```sql
CREATE TABLE agent_config (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    persona_name        TEXT NOT NULL DEFAULT 'Assistant',
    persona_description TEXT NOT NULL DEFAULT '',
    enabled_tools       TEXT[] NOT NULL DEFAULT '{rag_search,capture_lead,escalate}',
    blocked_topics      TEXT[] NOT NULL DEFAULT '{}',
    allowed_topics      TEXT[] NOT NULL DEFAULT '{}',
    max_tool_iterations INT NOT NULL DEFAULT 5,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table: cms_pages (Owner B's domain — A defines on Day 1)

```sql
CREATE TABLE cms_pages (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    slug         TEXT NOT NULL,
    content      TEXT NOT NULL,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, slug)
);
```

### Table: chunks (Owner B/C's domain — A defines on Day 1)

```sql
CREATE TABLE chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    page_id     UUID NOT NULL REFERENCES cms_pages(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   vector(768),          -- BGE-small dimension; change to 1536 if using OpenAI
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON chunks (tenant_id);   -- mandatory for tenant-filtered ANN search
```

### Table: leads (Owner B's domain — A defines on Day 1)

```sql
CREATE TABLE leads (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id       TEXT NOT NULL,
    visitor_name     TEXT NOT NULL,
    contact          TEXT NOT NULL,
    intent           TEXT NOT NULL,
    classifier_score FLOAT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table: escalations (Owner B's domain — A defines on Day 1)

```sql
CREATE TABLE escalations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    reason     TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open', 'resolved', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table: audit_log

```sql
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id    UUID NOT NULL,
    actor_role  TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_id   UUID,
    target_type TEXT,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

No RLS. Append-only. Erased-tenant rows retained. Only `tenant_manager` can read via route check.

### Table: tenant_costs

```sql
CREATE TABLE tenant_costs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date           DATE NOT NULL DEFAULT CURRENT_DATE,
    llm_tokens_in  BIGINT NOT NULL DEFAULT 0,
    llm_tokens_out BIGINT NOT NULL DEFAULT 0,
    embed_tokens   BIGINT NOT NULL DEFAULT 0,
    classify_calls BIGINT NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, date)
);
```

---

## Row-Level Security Policies

Applied in the initial Alembic migration alongside the table creation.

```sql
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON {table}
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::uuid);
```

Tables with RLS: `users`, `widgets`, `agent_config`, `cms_pages`, `chunks`, `leads`, `escalations`, `tenant_costs`

Tables without RLS: `tenants`, `audit_log` — route-level role checks only.

The `tenant_manager` role has no RLS bypass on any content table. It can write to `tenants`, append to `audit_log`, read aggregate `tenant_costs`, and execute the delete-only erasure path. Route-level `require_tenant_manager` enforces this.

---

## Per-Request RLS Session Variable

In `backend/app/tenancy/rls.py`:

```python
async def set_tenant_rls(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    # TRUE = transaction-scoped: resets automatically at transaction end
    # Safe for pooled connections — no explicit reset needed
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, TRUE)"),
        {"tid": str(tenant_id)}
    )
```

In `backend/app/dependencies.py`, `get_current_tenant_id`:
1. Decode JWT → extract `tenant_id` claim
2. Query `tenants` — verify `status == 'active'`
3. Call `set_tenant_rls(tenant_id, session)`
4. Return `uuid.UUID`

For `tenant_manager` requests: set sentinel `'00000000-0000-0000-0000-000000000000'` — matches no real row, RLS blocks all content tables safely.

---

## Repository Layer Scoping Convention

Every DB query touching a tenant-scoped table must include an explicit `.filter(Model.tenant_id == tenant_id)` even though RLS also enforces it. Defined in `backend/app/tenancy/repository.py` as a base mixin:

```python
class TenantRepository:
    model: type[Base]

    def scoped(self, session: AsyncSession, tenant_id: uuid.UUID):
        return session.query(self.model).filter(
            self.model.tenant_id == tenant_id   # belt
            # RLS also filters via app.tenant_id session var — suspenders
        )
```

All repository classes inherit from `TenantRepository`. Owner A blocks any PR that bypasses this mixin.

### Concrete Repository Pattern

Every model gets a concrete repository class in `backend/app/repositories/`. Owner A writes the platform repos (including `agent_config_repo.py`, needed at tenant provisioning time). Owner B writes the content-domain repos (chunk, lead, escalation, cms_page) and imports `agent_config_repo` from A.

```python
# backend/app/repositories/lead_repo.py  ← Owner B writes this
from app.tenancy.repository import TenantRepository
from app.models.lead import Lead

class LeadRepository(TenantRepository):
    model = Lead

    async def create(self, session, tenant_id, **kwargs) -> Lead:
        row = Lead(tenant_id=tenant_id, **kwargs)
        session.add(row)
        await session.flush()
        return row

    async def list_paginated(self, session, tenant_id, page, page_size) -> list[Lead]:
        return await self.scoped(session, tenant_id) \
            .offset((page - 1) * page_size).limit(page_size).all()
```

Services import from `repositories/`, never write raw queries inline:
```python
# backend/app/services/agent.py
from app.repositories.lead_repo import LeadRepository
lead_repo = LeadRepository()
```

`backend/app/repositories/base.py` re-exports `TenantRepository` so other owners have one import path:
```python
from app.repositories.base import TenantRepository
```

---

## Three Roles

| Role | `tenant_id` on user row | Powers |
|---|---|---|
| `tenant_manager` | NULL | Provision/suspend/erase tenants, invite first admin, read aggregate costs |
| `tenant_admin` | Non-null | Manage CMS, configure agent/widgets/guardrails, view own leads |
| `member` | N/A — anonymous widget visitor | Chat only |

Defined in `backend/app/auth/roles.py`:
```python
class Role(str, Enum):
    tenant_manager = "tenant_manager"
    tenant_admin = "tenant_admin"
    member = "member"

def require_role(role: Role) -> Depends: ...
```

---

## Tenant Provisioning Flow

**`POST /api/v1/platform/tenants`** — `tenant_manager` only

```json
Request:  { "slug": "acme-corp", "name": "Acme Corporation", "first_admin_email": "admin@acme.com" }
Response: { "tenant_id": "uuid", "invite_token": "uuid" }
```

Steps (atomic):
1. Validate `slug` uniqueness — 409 if taken
2. Insert `tenants` row
3. Insert `agent_config` seed row with defaults
4. Generate one-time invite token (UUID, stored hashed, expires 24h)
5. Write `audit_log`: `{ action: "tenant.create" }`

---

## Tenant Erasure Flow

**`DELETE /api/v1/platform/tenants/{tenant_id}`** — `tenant_manager` only

The manager destroys without reading. Steps:
1. Set `status = 'erasing'` (prevents concurrent erasure)
2. Write `audit_log`: `{ action: "tenant.erase_started" }`
3. In one transaction, delete in FK-safe order: `chunks`, `leads`, `escalations`, `cms_pages`, `agent_config`, `widgets`, `users`, `tenant_costs` — then set `status = 'erased'`
4. Commit
5. Background task: flush Redis keys `conversation:{tenant_id}:*` and `ratelimit:{tenant_id}:*`
6. Background task: delete MinIO/storage objects under `tenants/{tenant_id}/`
7. Write `audit_log`: `{ action: "tenant.erase_complete" }`

`audit_log` rows for erased tenants are never deleted — they are the compliance trail.

---

## Per-Tenant Rate Limiting

`backend/app/services/rate_limiter.py` — Redis-backed, called by Owner B.

| Action | Limit | Window | Scope |
|---|---|---|---|
| `chat` | 60 | 1 hour | per session_id |
| `capture_lead` | 5 | 1 hour | per session_id |
| `llm_call` | 1000 | 1 day UTC | per tenant |
| `embed` | 2000 | 1 day UTC | per tenant |
| `classify` | 5000 | 1 day UTC | per tenant |

Redis key: `ratelimit:{tenant_id}:{action}:{window_epoch}`

```python
async def check_rate_limit(redis, tenant_id, session_id, action) -> bool
async def increment_rate_limit(redis, tenant_id, session_id, action) -> None
```

---

## Per-Tenant Cost Attribution

`backend/app/services/cost_meter.py` — Owner B calls after every LLM/embed call.

```python
async def record_llm_usage(session, tenant_id, tokens_in, tokens_out) -> None
async def record_embed_usage(session, tenant_id, tokens) -> None
async def record_classify_call(session, tenant_id) -> None
```

Upserts using `ON CONFLICT (tenant_id, date) DO UPDATE SET ... = ... + excluded....`

---

## Vault Secrets

`vault/init.sh` seeds on first `docker-compose up`:

| Path | Key | Day-1 value |
|---|---|---|
| `secret/svc/modelserver` | `token` | random 32-byte hex |
| `secret/svc/guardrails` | `token` | random 32-byte hex |
| `secret/widget/signing_key` | `key` | random 32-byte hex |
| `secret/db/password` | `password` | docker-compose value |
| `secret/llm/api_key` | `key` | empty — team fills |
| `secret/embed/api_key` | `key` | empty — team fills |
| `secret/minio/access_key` | `key` | `minioadmin` (dev only) |
| `secret/minio/secret_key` | `key` | `minioadmin` (dev only) |

App reads all secrets at startup in `backend/app/lifespan.py`. Missing required secret = startup failure.

---

## Docker Compose

Owner A owns `docker-compose.yml` entirely.

| Service | Build context | Internal port | Health check |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | 5432 | `pg_isready` |
| `redis` | `redis:7-alpine` | 6379 | `redis-cli ping` |
| `vault` | `hashicorp/vault:1.15` | 8200 | `GET /v1/sys/health` |
| `minio` | `minio/minio:latest` | 9000 | `curl -f http://localhost:9000/minio/health/live` |
| `jaeger` | `jaegertracing/all-in-one:1.55` | 4317 (OTLP gRPC), 16686 (UI) | `GET /` HTTP 200 on port 14269 |
| `backend` | `./backend` | 8000 | `GET /health` |
| `modelserver` | `./modelserver` | 8001 | `GET /health` |
| `guardrails` | `./guardrails` | 8002 | `GET /health` |
| `admin` | `./admin` | 8501 | `GET /` HTTP 200 |
| `widget` | `./widget` | 3000 | `GET /widget.js` HTTP 200 |

MinIO is used for tenant blob storage (file uploads, async exports). Objects are keyed `tenants/{tenant_id}/...`. The erasure flow flushes all keys under the tenant's prefix.

Jaeger receives OpenTelemetry traces from the backend via `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317`. Owner C wires real spans into `backend/app/tracing.py`. The Jaeger UI is available at `http://localhost:16686` during local development.

---

## FastAPI main.py — Auto-Discovery

`backend/app/main.py` — written by Owner A on Day 1, nobody else edits it.

```python
import importlib, pkgutil
import app.routes as routes_pkg
from app.lifespan import lifespan

app = FastAPI(title="Concierge API", version="0.1.0", lifespan=lifespan)

for module_info in pkgutil.iter_modules(routes_pkg.__path__):
    module = importlib.import_module(f"app.routes.{module_info.name}")
    if hasattr(module, "router"):
        app.include_router(module.router)
```

Owner A stubs `cms.py`, `chat.py`, and `widget.py` on Day 1 with routes returning `501 Not Implemented`. When B and D replace those files with their real implementations, the app picks them up without any `main.py` edit.

---

## Seeded Tenants (Day 1 Required)

In the initial migration or a separate data migration:

```
Tenant A:  id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  slug = "acme"
Tenant B:  id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"  slug = "globex"

admin@acme.com          role=tenant_admin    tenant_id=aaaa...
admin@globex.com        role=tenant_admin    tenant_id=bbbb...
platform@concierge.test role=tenant_manager  tenant_id=NULL
```

These exact UUIDs are used in all eval fixtures and red-team test prompts.

---

## Day 1 Checklist

- [ ] `docker-compose up` — all services healthy
- [ ] Vault seeded with all paths
- [ ] pgvector extension enabled
- [ ] Initial migration with ALL tables applied and RLS active
- [ ] `GET /health` returns 200
- [ ] `POST /api/v1/auth/login` returns a JWT
- [ ] `get_current_tenant_id` dependency tested (correct tenant, wrong tenant → 403)
- [ ] `POST /api/v1/platform/tenants` works for `tenant_manager`
- [ ] Two seeded tenants readable
- [ ] Vault service tokens readable by Owner C from Day 1
- [ ] Stubs for `cms.py`, `chat.py`, `widget.py` committed (return 501)
- [ ] RLS isolation integration test passing: Tenant A cannot see Tenant B rows

---

## Edge Cases

**Connection pool RLS leak:** Transaction-scoped `set_config(..., TRUE)` resets automatically at transaction end. Integration test: two sequential requests from different tenants on the same pool — assert no cross-tenant rows returned.

**Erasure race:** `status = 'erasing'` set before work begins. Second concurrent call sees non-active status, returns 409.

**Suspended tenant:** `get_current_tenant_id` checks `status == 'active'` on every request. Suspending a tenant instantly denies all existing JWTs — no token revocation list needed.

**`tenant_id` from request body:** Auth middleware reads `tenant_id` only from the verified JWT. CI test: send a request with a spoofed `tenant_id` in the body, assert it is ignored.
