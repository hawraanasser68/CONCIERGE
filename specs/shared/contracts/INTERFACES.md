# Shared Interface Contracts

**Status: FROZEN — no changes without team discussion and updated date below**
**Last frozen: 2026-05-26**

These are the cross-owner API contracts. Every owner codes against these shapes exactly.
If a contract must change, open a PR that updates this file first, get approval from all affected owners, then change the implementations.

---

## 1. tenant_id Convention

| Field | Value |
|---|---|
| Type | `UUID` (Python: `uuid.UUID`, Postgres: `UUID`) |
| Column name | `tenant_id` everywhere, no exceptions |
| RLS session variable | `app.tenant_id` |
| Source of truth for a request | The verified JWT token — never a request body field |
| Python dependency name | `get_current_tenant_id` — returns `uuid.UUID` |

**Critical rule:** `tenant_id` is NEVER read from `request.body`, `request.query_params`, or any client-supplied field. It comes exclusively from the decoded and verified token via the `get_current_tenant_id` FastAPI dependency. Trusting `tenant_id` from the body is a one-line cross-tenant breach.

---

## 2. Model Server Contract

**Owner C provides. Owner B consumes.**

### POST /classify

**Request:**
```json
{
  "text": "string — the raw visitor message",
  "tenant_id": "string — UUID formatted as string"
}
```

**Response (200 OK):**
```json
{
  "intent": "string — one of: spam | faq | lead | escalate | ambiguous",
  "confidence": 0.92
}
```

**Intent values and their routing consequences:**

| Intent | Confidence threshold | Action |
|---|---|---|
| `spam` | any | Drop message, return generic refusal, do not log content |
| `faq` | >= 0.80 | Route to RAG workflow, answer directly without agent |
| `lead` | >= 0.80 | Route to `capture_lead` workflow directly |
| `escalate` | >= 0.80 | Route to `escalate` workflow directly |
| `ambiguous` | any | Hand to tool-calling agent |

If confidence < 0.80, treat as `ambiguous` regardless of intent label.

**Authentication:** `Authorization: Bearer <service_token>` from Vault secret `secret/svc/modelserver`

**Error responses:**
```json
{ "error": "string description", "code": "MODEL_NOT_LOADED | INVALID_INPUT | UNAUTHORIZED" }
```

HTTP 401 — missing or invalid credential
HTTP 422 — malformed request body
HTTP 503 — model artifact not loaded

---

## 3. Guardrails Sidecar Contract

**Owner C provides. Owner B and the API middleware consume.**

Called twice per turn: once before routing (input check), once before sending the response back (output check).

### POST /check/input

**Request:**
```json
{
  "message": "string — raw visitor message",
  "tenant_id": "string — UUID as string",
  "session_id": "string — conversation session UUID as string",
  "direction": "input"
}
```

**Response (200 OK — allowed):**
```json
{
  "allowed": true,
  "flagged_categories": [],
  "redacted_message": "string — message with PII/secrets replaced by [REDACTED]"
}
```

**Response (200 OK — blocked):**
```json
{
  "allowed": false,
  "flagged_categories": ["prompt_injection", "cross_tenant_probe", "jailbreak", "pii"],
  "redacted_message": "string — redacted version of the message",
  "block_reason": "string — safe description shown to caller, NOT internal reasoning"
}
```

`flagged_categories` values: `prompt_injection | cross_tenant_probe | jailbreak | pii | off_topic`

### POST /check/output

**Request:**
```json
{
  "message": "string — LLM-generated response text",
  "tenant_id": "string — UUID as string",
  "session_id": "string — UUID as string",
  "direction": "output"
}
```

**Response:** Same shape as `/check/input`.

**Authentication:** `Authorization: Bearer <service_token>` from Vault secret `secret/svc/guardrails`

**Critical behavior on sidecar unavailability:** Fail closed — block the message and return HTTP 503 to the chat endpoint. Never allow a message through because the sidecar is unreachable. The API must treat a 5xx from the sidecar the same as `allowed: false`.

---

## 4. Widget Token (JWT) Claims

**Owner A defines the signing and verification middleware. Owner D defines the token exchange endpoint. Both must agree on this exact shape — no deviations.**

### Token Claims

```json
{
  "tenant_id": "string — UUID as string",
  "widget_id": "string — UUID as string",
  "origin": "string — the Origin header value that was validated at issuance",
  "session_id": "string — UUID generated fresh at token issuance",
  "type": "widget_session",
  "iat": 1748900000,
  "exp": 1748903600
}
```

**TTL:** 1 hour (`exp = iat + 3600`)
**Algorithm:** `HS256`
**Secret:** From Vault at path `secret/widget/signing_key`, key `key`

### Validation Rules (enforced by A's auth middleware on every chat request)

Checked in this order — fail on first violation:

1. JWT signature is valid (correct secret, correct algorithm)
2. `exp` has not passed (clock skew tolerance: 30 seconds)
3. `type` claim equals `"widget_session"`
4. `origin` claim matches the incoming `Origin` header exactly — return HTTP 403 if mismatch
5. `widget_id` exists in the `widgets` table and `is_active = true`
6. `tenant_id` claim matches `widgets.tenant_id` for the given `widget_id`
7. The tenant exists and has `status = 'active'`

Any failure returns HTTP 401 (signature/expiry) or HTTP 403 (origin mismatch, inactive widget, suspended tenant).

### Token Exchange Request

**Endpoint:** `POST /api/v1/widget/token` (Owner D implements the endpoint, Owner A implements the signing logic called by it)

**Request:**
```json
{
  "widget_id": "string — UUID",
  "origin": "string — the embedding site's origin, e.g. https://example.com"
}
```

**Response (200 OK):**
```json
{
  "token": "string — signed JWT",
  "session_id": "string — UUID, same value as in the token claims",
  "expires_at": "2026-05-26T13:00:00Z"
}
```

**Response (403 Forbidden — origin not in allowlist):**
```json
{ "error": "Origin not allowed", "code": "ORIGIN_BLOCKED" }
```

---

## 5. Tool Schemas (Agent Tools)

**Owner B implements the tools. These schemas are frozen.**

**Critical architecture — two distinct layers per tool:**

1. **LLM-facing input schema** — the `input_schema` sent to Claude in the API call. Contains only what the LLM should supply. `tenant_id` is **NOT** in this schema. The LLM never provides it.
2. **Python function signature** — receives `tenant_id` from the `get_current_tenant_id` FastAPI dependency, injected by the request context from the verified JWT. Cannot be overridden by the LLM's tool call output.

Putting `tenant_id` in the LLM-facing schema would be a one-line cross-tenant breach: a prompt injection could then override it.

---

### rag_search

**LLM-facing input schema (what Claude fills in):**
```json
{
  "query": "string — the search query, max 500 characters"
}
```

**Python function signature (server-side execution):**
```python
async def rag_search(
    query: str,
    tenant_id: uuid.UUID,       # injected from get_current_tenant_id — never from LLM args
    session: AsyncSession,
) -> dict
```

**Output from tool back to agent:**
```json
{
  "chunks": [
    {
      "content": "string — retrieved text chunk",
      "source_url": "string or null",
      "score": 0.87
    }
  ],
  "retrieved_count": 5
}
```

Empty result (no chunks found):
```json
{ "chunks": [], "retrieved_count": 0 }
```

---

### capture_lead

**LLM-facing input schema (what Claude fills in):**
```json
{
  "name": "string — visitor name, max 255 characters",
  "contact": "string — email or phone number, max 255 characters",
  "intent": "string — what the visitor wants, max 1000 characters"
}
```

**Python function signature:**
```python
async def capture_lead(
    name: str,
    contact: str,
    intent: str,
    tenant_id: uuid.UUID,       # injected from dependency — not from LLM args
    session_id: str,            # from verified JWT
    session: AsyncSession,
    redis: Redis,
) -> dict
```

**Validation rules enforced before any write:**
- `contact` must match email regex OR E.164 phone regex — reject if neither
- `name` must be non-empty after stripping whitespace
- `tenant_id` is sourced from the verified JWT via dependency injection — a cross-tenant write is architecturally impossible regardless of what the LLM produces
- Rate limit: max 5 `capture_lead` calls per `session_id` per hour

**Output (success):**
```json
{
  "lead_id": "string — UUID of the created lead row",
  "captured": true
}
```

**Output (validation failure or rate limit):**
```json
{
  "captured": false,
  "reason": "string — human-readable reason"
}
```

---

### escalate

**LLM-facing input schema (what Claude fills in):**
```json
{
  "reason": "string — why escalation is needed, max 500 characters",
  "conversation_id": "string — the session_id UUID as string"
}
```

**Python function signature:**
```python
async def escalate(
    reason: str,
    conversation_id: str,
    tenant_id: uuid.UUID,       # injected from dependency — not from LLM args
    session: AsyncSession,
) -> dict
```

**Output:**
```json
{
  "escalated": true,
  "ticket_id": "string — UUID of the escalation row"
}
```

---

## 6. Redis Key Naming Pattern

**Owner B writes session data. Owner D's widget exchange creates the session_id. Owner C may read for guardrail context.**

Key pattern:
```
conversation:{tenant_id}:{session_id}
```

Example:
```
conversation:550e8400-e29b-41d4-a716-446655440000:f47ac10b-58cc-4372-a567-0e02b2c3d479
```

**Data type:** Redis List. Each element is a JSON string. Newest message is prepended (LPUSH). Read with LRANGE 0 19 for last 20.

**Each list element:**
```json
{
  "role": "user",
  "content": "string — redacted content (PII already removed by guardrails)",
  "timestamp": "2026-05-26T10:00:00Z"
}
```

**TTL:** 30 minutes, refreshed on every write via `EXPIRE`. Justification: a concierge that forgets 2 messages ago is useless; anonymous visitor chat stored indefinitely is a privacy liability.

**Max entries:** 20 messages. After each LPUSH, call `LTRIM conversation:{tid}:{sid} 0 19` to enforce the cap.

**Session ID source:** Generated at widget token exchange by Owner D's endpoint, embedded in the JWT, extracted from the verified token on every request. Never generated by the client.

---

## 7. Alembic Migration Ownership

**Only Owner A generates migration files. No exceptions.**

Migration workflow for other owners:
1. Define or modify a SQLAlchemy model in your module's `models.py`
2. Open a PR with the model change only — no migration file
3. Tag Owner A in the PR
4. Owner A generates the migration with `alembic revision --autogenerate -m "..."` and commits it to the same PR or a follow-up

Never run `alembic revision` outside of Owner A's hands. Two migration files pointing to the same parent break the chain.

---

## 8. docker-compose.yml Ownership

**Owner A owns this file. All changes go through Owner A.**

To add a new service: open a PR containing only your `services/{name}/Dockerfile` and `services/{name}/` directory contents. Do not touch `docker-compose.yml` in your PR. Owner A adds your service block.

Each service block must include:
- A `healthcheck` with a meaningful test
- `depends_on` with `condition: service_healthy` for every service it calls
- Environment variables sourced from `.env` — no hardcoded secrets

---

## 9. Service-to-Service Authentication

All HTTP calls between internal services use Bearer token authentication. Network adjacency is not authentication.

| Caller | Callee | Vault Secret Path | Header |
|---|---|---|---|
| API | Model Server | `secret/svc/modelserver` → `token` field | `Authorization: Bearer <token>` |
| API | Guardrails Sidecar | `secret/svc/guardrails` → `token` field | `Authorization: Bearer <token>` |

Tokens are read at startup from Vault and cached in memory. If Vault is unreachable at startup, the service must fail to start (not start with empty credentials).

---

## 10. FastAPI Router Auto-Discovery

Owner A writes `backend/app/main.py` on Day 1. Nobody else modifies this file.

All route files live in one flat directory: `backend/app/routes/`. Any file in that directory that exposes a variable named `router` of type `fastapi.APIRouter` is automatically registered.

```python
# backend/app/main.py — written by Owner A, never touched again
import importlib
import pkgutil
import app.routes as routes_pkg

app = FastAPI(...)

for module_info in pkgutil.iter_modules(routes_pkg.__path__):
    module = importlib.import_module(f"app.routes.{module_info.name}")
    if hasattr(module, "router"):
        app.include_router(module.router)
```

Each route file must declare its own `prefix` and `tags`:
```python
# backend/app/routes/chat.py — Owner B drops this file
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
```

To add a new route group: drop a new file in `backend/app/routes/`. No `main.py` edit needed. Owner A stubs every expected route file on Day 1 so the app starts even before other owners write their real implementations.

Route file-to-prefix mapping (agreed Day 1, frozen):

| File | Prefix | Owner |
|---|---|---|
| `routes/health.py` | `/health` | A |
| `routes/auth.py` | `/api/v1/auth` | A |
| `routes/manager.py` | `/api/v1/platform` | A |
| `routes/tenant_admin.py` | `/api/v1/admin` | A (entirely — widgets, leads, escalations, agent-config) |
| `routes/cms.py` | `/api/v1/cms` | B |
| `routes/chat.py` | `/api/v1/chat` | B |
| `routes/widget.py` | `/api/v1/widget` | D |

---

## 11. X-Session-Id Header

Every chat request from the widget carries the session ID in a header so the API can scope Redis reads without parsing the JWT a second time.

```
X-Session-Id: f47ac10b-58cc-4372-a567-0e02b2c3d479
```

The API validates that this header value matches the `session_id` claim in the JWT. If they differ, reject with HTTP 400. This prevents a visitor from injecting a different session ID to read another session's context.
