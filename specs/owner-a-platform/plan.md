# Owner A — Implementation Plan
## Platform, Tenancy, Isolation & Provisioning

---

## Summary

Owner A builds the foundation every other owner depends on. The deliverable is a running multi-tenant PostgreSQL database with Row-Level Security, a FastAPI application skeleton with auto-discovery routing, a complete auth stack, and all Docker services wired together. Nothing else can be built until Day 1 deliverables are complete.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Web framework | FastAPI (async) | Native async, dependency injection, OpenAPI docs |
| ORM | SQLAlchemy 2.x (async) | Async sessions, declarative models, Alembic integration |
| Migrations | Alembic | Only A runs migrations — single chain |
| Auth | fastapi-users | JWT issuance, password hashing, user management out of the box |
| JWT signing | PyJWT | Widget token sign/verify |
| Vault client | hvac | Secret fetch at startup |
| Postgres driver | asyncpg | Async Postgres, required for SQLAlchemy async |
| Vector extension | pgvector | ANN search on chunk embeddings |
| Tracing | opentelemetry-sdk | Stubs that Owner C fills |
| Logging | structlog | Structured JSON logs |
| Config | pydantic-settings | Type-safe env/Vault config, `extra="forbid"` |
| Dependency management | uv | Fast, lock-file based |

---

## Architecture Decisions

### Multi-tenancy Strategy
Row-Level Security (RLS) via transaction-scoped `set_config('app.tenant_id', ..., TRUE)`. Belt-and-suspenders: every query also includes an explicit `WHERE tenant_id = :tid`. Neither alone is sufficient; both together mean a missing SQL filter still has RLS as backstop, and a bypassed RLS policy still has the SQL filter.

### Why transaction-scoped (not session-scoped)?
`set_config(..., TRUE)` resets at transaction end automatically. Safe for connection pools — no explicit reset needed, no risk of leaking one tenant's context into another's request.

### Alembic Ownership
Single owner generates all migration files. Two owners running `alembic revision` simultaneously break the chain (two files pointing to the same parent). All tables defined in one Day-1 migration so nobody is ever waiting on A mid-week.

### Auto-Discovery Router
`pkgutil.iter_modules` scans `backend/app/routes/`. Any file with a `router: APIRouter` variable is registered. `main.py` is written once and never touched again. Eliminates merge conflicts on the app entrypoint.

### Repository Pattern
`TenantRepository` base mixin enforces `WHERE tenant_id = :tid` on every query. All concrete repos inherit from it. A blocks any PR that bypasses the mixin.

---

## Data Model (All Tables — Owner A defines, others map to)

```
tenants          — no RLS, role checks only
users            — RLS
widgets          — RLS
agent_config     — RLS (1 row per tenant, seeded at provisioning)
cms_pages        — RLS
chunks           — RLS, vector(768) column + IVFFlat index
leads            — RLS
escalations      — RLS
audit_log        — no RLS, append-only, retained after erasure
tenant_costs     — RLS, daily upsert
```

---

## Key Constraints

- `tenant_id` sourced ONLY from verified JWT — never request body
- Tenant manager uses sentinel UUID `00000000-0000-0000-0000-000000000000`
- Erasure: delete-only path, no reads, retains `audit_log` rows
- Vault unreachable at startup → service fails to start (not start with empty creds)
- All 10 docker-compose services must pass healthchecks before backend starts

---

## Dependencies on Other Owners

| Needs | From | When |
|---|---|---|
| Tool schemas in INTERFACES.md | Owner B | Day 1 (before writing guardrails middleware) |
| modelserver + guardrails stubs live | Owner C | Day 1 (smoke test requires /health on both) |
