# Concierge — Design Document

**Owner:** Owner A  
**Last updated:** 2026-05-26

---

## 1. Tenant Isolation Strategy

Every piece of data in this system belongs to exactly one tenant. Isolation is enforced at two independent layers — if either one has a bug, the other still holds.

### Layer 1 — Row-Level Security (RLS)

Every tenant-scoped table has a Postgres RLS policy:

```sql
CREATE POLICY tenant_isolation ON widgets
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::uuid);
```

The session variable `app.tenant_id` is set at the start of every request by `get_current_tenant_id` in `dependencies.py`. The `TRUE` flag makes it transaction-scoped — it resets automatically when the transaction ends, so there is no risk of a pooled connection leaking one tenant's context into another tenant's request.

Six tables use `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`: `widgets`, `agent_config`, `cms_pages`, `chunks`, `leads`, `escalations`, `tenant_costs`. The DB owner is also subject to RLS on these tables.

`users` uses `ENABLE` only (not `FORCE`) because the login flow queries by email before any tenant context is established.

### Layer 2 — Explicit WHERE Clause (Belt and Suspenders)

Every repository method in `app/repositories/` starts from `TenantRepository.scoped(tenant_id)`, which returns a `SELECT` pre-filtered by `tenant_id`. No raw `select(Model)` is permitted in any repo — Owner A reviews and blocks any PR that bypasses this convention.

### Why Both?

RLS alone is vulnerable to mistakes in session variable management. The explicit `WHERE` clause alone is vulnerable to programmer error (forgetting to add it). Together, a bug in one layer cannot cause a cross-tenant data leak.

### What Has No RLS

- `tenants` — no `tenant_id` column; access controlled by `require_role(Role.tenant_manager)` at the route level.
- `audit_log` — append-only compliance trail; rows for erased tenants are never deleted.

---

## 2. tenant_id Source of Truth

`tenant_id` is read from **exactly one place**: the verified JWT, via the `get_current_tenant_id` FastAPI dependency.

It is **never** read from the request body, query parameters, or any client-supplied field. A single line that trusts `request.body["tenant_id"]` is a cross-tenant breach — any visitor could forge it.

For widget chat requests, `tenant_id` comes from the widget JWT (`verify_widget_jwt` in `auth/widget_token.py`). The JWT is signed with a secret from Vault. The 7-step validation chain in `get_widget_session` ensures the token is valid, unexpired, correctly typed, origin-matched, and that the widget and tenant are both active before any `tenant_id` is trusted.

---

## 3. Role Model

| Role | `tenant_id` on user row | Can do |
|---|---|---|
| `tenant_manager` | NULL | Provision/suspend/erase tenants, read aggregate costs, write audit log |
| `tenant_admin` | Non-null | Manage CMS, configure agent/widgets, view own leads and escalations |
| `member` | N/A — anonymous widget visitor | Chat only, via widget JWT |

Roles are enforced at the route level using `require_role()` from `app/auth/roles.py`. Every protected route declares its required role explicitly — there is no implicit role inheritance.

The `tenant_manager` role cannot read tenant content (CMS, leads, conversations). The RLS sentinel `'00000000-0000-0000-0000-000000000000'` matches no real row, so even if a manager bypasses the route check, RLS blocks all content reads.

---

## 4. Tenant Lifecycle

```
provisioned → active → suspended → erasing → erased
```

- **active**: all requests allowed
- **suspended**: `get_current_tenant_id` returns 403 on every request — no token revocation needed, suspension takes effect instantly
- **erasing**: set before deletion begins; a second concurrent erase call gets 409
- **erased**: data deleted, `erased_at` timestamp set, `audit_log` rows retained permanently

The erasure flow deletes rows in FK-safe order: `chunks → leads → escalations → cms_pages → agent_config → widgets → tenant_costs → users`. Tenant row itself is marked `erased`, not deleted, so audit logs retain a valid `target_id` reference.

---

## 5. Authentication Architecture

### Admin Users (fastapi-users)

Login via `POST /api/v1/auth/login` returns a Bearer JWT. The JWT is signed with a key from Vault (`secret/widget/signing_key`). TTL is 24 hours. The key is read at startup — rotating the key requires a rolling restart.

`get_current_user` uses fastapi-users' `current_user(active=True)` dependency. `get_current_tenant_id` validates the tenant is still active on every request — suspending a tenant takes effect without token revocation.

### Widget Sessions (custom JWT)

Widget visitors never have user accounts. Instead, Owner D's token exchange endpoint (`POST /api/v1/widget/token`) calls `sign_widget_jwt()` to issue a 1-hour HS256 token containing `tenant_id`, `widget_id`, `origin`, and `session_id`.

Every subsequent chat request validates this token through the 7-step chain in `get_widget_session`. The `X-Session-Id` header must match the JWT claim to prevent session injection.

### Service-to-Service

The backend calls the modelserver and guardrails sidecar using Bearer tokens from Vault (`secret/svc/modelserver`, `secret/svc/guardrails`). Network adjacency is not authentication. If Vault is unreachable at startup, the backend refuses to start.

---

## 6. Per-Tenant Rate Limiting

Redis-backed, keyed as `ratelimit:{tenant_id}:{action}:{window_epoch}`. The window epoch is `floor(now / window_seconds)` so keys expire naturally when the window rolls over — no explicit cleanup needed.

| Action | Limit | Window | Scope |
|---|---|---|---|
| `chat` | 60 | 1 hour | per session_id |
| `capture_lead` | 5 | 1 hour | per session_id |
| `llm_call` | 1000 | 1 day UTC | per tenant |
| `embed` | 2000 | 1 day UTC | per tenant |
| `classify` | 5000 | 1 day UTC | per tenant |

TTL is set to 2× the window on every `increment_rate_limit` call so Redis auto-cleans stale keys.

---

## 7. Per-Tenant Cost Attribution

After every LLM/embed/classify call, Owner B calls one of the three functions in `cost_meter.py`. Each call upserts the daily row in `tenant_costs` using `ON CONFLICT (tenant_id, date) DO UPDATE` — the operation is idempotent and safe to retry.

Costs are attributed to the tenant that made the request (from the verified JWT), never self-reported by the client.

---

## 8. Scaling Story

**Horizontal scaling:** The backend is stateless — all shared state lives in Postgres, Redis, and Vault. Adding more backend replicas requires no coordination. The only sticky state is the DB connection pool, which is sized to `pool_size=10, max_overflow=20` per instance.

**RLS + connection pooling:** Transaction-scoped `set_config` resets automatically. Multiple tenants can share the same connection pool without risk of context leakage. Integration test: two sequential requests from different tenants on the same pool assert no cross-tenant rows returned.

**Redis session memory:** Capped at 20 messages per session with a 30-minute TTL. At scale, Redis memory is bounded by `active_sessions × 20 × avg_message_size`. TTL-based expiry means no explicit cleanup job is needed.

**pgvector ANN search:** The IVFFlat index (`lists=100`) provides sub-linear search at the cost of approximate results. Every ANN query includes `WHERE tenant_id = :tid` before the vector scan — this filters the candidate set before the index is consulted, keeping cross-tenant vector comparisons impossible.

**Tenant erasure at scale:** Erasure deletes rows in a single transaction ordered by FK dependency. For tenants with large `chunks` tables, this may take several seconds. The `status='erasing'` flag prevents concurrent erasure and allows the operation to be safely retried if it fails mid-flight.

---

## 9. Scaling Story: 10 Tenants vs 1,000 Tenants

### At 10 tenants (current state — works today)

The stack runs comfortably on a single Postgres instance, single Redis node, and one backend replica. Every component is either stateless (backend, modelserver, guardrails) or single-instance with no coordination overhead (Postgres, Redis). RLS adds a per-query session variable lookup — negligible at this scale. The IVFFlat pgvector index performs well with a small total chunk count.

**Bottleneck:** none. Any single component can handle 10 tenants with headroom.

### At 1,000 tenants — where it breaks and what changes

| Component | What breaks | Fix |
|---|---|---|
| **Postgres — connection pool** | 1,000 concurrent tenants × 20 connections/backend = 20,000 connections. Postgres max_connections default is 100. | Add PgBouncer connection pooler in transaction mode. Backend targets PgBouncer; Postgres sees O(100) connections regardless of replica count. |
| **pgvector ANN search** | A single `chunks` table with 1,000 tenants × 500 pages × 4 chunks = 2M+ rows. Even with `WHERE tenant_id = :tid`, IVFFlat scans the full index then filters. Query time degrades. | Partition `chunks` by `tenant_id` (Postgres declarative partitioning). Each partition has its own IVFFlat index; ANN search touches only one partition. |
| **Postgres — write throughput** | `tenant_costs` gets one upsert per LLM/embed call. At 1,000 active tenants × 100 calls/min = 100k writes/min. Single Postgres primary saturates around 10k-50k writes/min. | Batch cost increments via a Redis counter (INCR) and flush to Postgres every 60 seconds in a background worker. Trades real-time accuracy for write headroom. |
| **Redis — rate limiter keys** | Each active session holds 5 rate-limit keys (chat, capture_lead, llm_call, embed, classify). At 1,000 tenants × 100 active sessions = 500k keys. Redis handles this fine but memory needs monitoring. | Set a max memory policy (`allkeys-lru`) and monitor `used_memory`. At 5 bytes/key avg, 500k keys ≈ 2.5 MB — not a concern until O(10M) keys. |
| **Modelserver — classify latency** | Classical TF-IDF + LR is CPU-bound at ~0.18ms/call. At 1,000 tenants × 10 req/s = 10,000 classifies/s. Single-threaded uvicorn worker saturates. | Run modelserver with `--workers 4` (multi-process uvicorn). The joblib model is read-only; no shared state between workers. Horizontal scaling requires no coordination. |
| **Guardrails sidecar** | Presidio NER runs per message. At 10,000 messages/s, the single sidecar becomes the bottleneck before the LLM does. | Scale guardrails horizontally behind an internal load balancer. Each instance is stateless. |

### Next single bottleneck beyond 1,000 tenants

**Postgres write path** (the `tenant_costs` upsert storm) is the first failure mode. Fix: Redis-buffered cost counters. After that, **pgvector partition fan-out** at 10M+ chunks becomes the limit — at which point a dedicated vector database (Qdrant, Weaviate) with native multi-tenancy is the right next step.
