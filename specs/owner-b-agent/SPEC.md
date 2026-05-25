# Owner B — Agent, RAG & Memory

**Owner:** Owner B
**Day-1 deliverable:** Tool schemas committed to INTERFACES.md — before any code

---

## Scope

Owner B owns everything between the message arriving at the backend and the response leaving it:

- Classifier-driven router (`backend/app/services/router.py`) — workflow for easy turns
- Tool-calling agent (`backend/app/services/agent.py`) — for ambiguous/multi-step turns
- Three agent tools in `backend/app/tools/`
- CMS CRUD endpoints — `backend/app/routes/cms.py`
- Embedding pipeline: CMS pages → embeddings → tenant-filtered pgvector
- RAG retrieval: chunking, ANN search, one justified improvement
- Redis session memory scoped per conversation
- LLM client adapter (`backend/app/services/llm_client.py`)
- Embeddings client (`backend/app/services/embeddings_client.py`) — calls modelserver `/embed`
- Prompts in `prompts/` (root) — version-controlled, persona injected at runtime
- Agent tool-selection golden set (15 examples)
- RAG golden set (15 triples)
- Cost attribution calls (calls Owner A's `cost_meter.py`)
- `docs/DECISIONS.md` — documents: agent-vs-workflow-vs-hybrid rationale, chunking strategy choice, embedding model choice, caching policy (what is cached, what is not, and why)
- `docs/EVALS.md` (co-written with Owner C) — describes what each CI gate measures, how to interpret scores, RAG judge agreement methodology
- Router efficiency metric: fraction of turns handled without the agent, reported per tenant in EVALS.md

Owner B does NOT own:
- Auth, RLS, migrations, docker-compose (Owner A)
- Classifier training, model server implementation, guardrails sidecar (Owner C)
- React widget, admin Streamlit UI, CI pipeline (Owner D)

---

## Files and Directories — What Owner B Writes

```
prompts/                                 ← root-level, version-controlled
  system_agent.md                        ← agent system prompt; {persona_name}, {persona_description}, {tenant_name}
  router_classifier.md                   ← reference for classifier-routed workflows
  tenant_persona_template.md             ← injected tenant persona block

docs/
  DECISIONS.md                           ← B writes (see Scope)
  EVALS.md                               ← B + C co-write (see Scope)

backend/
  app/
    routes/
      cms.py                             ← CMS CRUD (replaces Owner A's Day-1 stub)
      chat.py                            ← POST /api/v1/chat/message (replaces stub)

    repositories/
      chunk_repo.py                      ← ANN search query (tenant-filtered pgvector)
      lead_repo.py                       ← insert lead, paginated list
      escalation_repo.py                 ← insert escalation, update status
      cms_page_repo.py                   ← CRUD for CMS pages, publish toggle
      # agent_config_repo.py is owned by Owner A — import from there

    services/
      llm_client.py                      ← Anthropic SDK adapter (Claude)
      embeddings_client.py               ← calls modelserver POST /embed
      classifier_client.py               ← calls modelserver POST /classify
      guardrails_client.py               ← calls guardrails POST /check/input|output
      rag.py                             ← retrieval: embed query → pgvector ANN → rerank → return chunks
      router.py                          ← classifier-driven workflow (spam/faq/lead/escalate/agent)
      agent.py                           ← bounded tool-calling LLM loop

    tools/
      rag_search.py
      capture_lead.py
      escalate.py

  evals/
    classifier/
      golden.jsonl                       ← held-out test examples for classifier eval
      run.py
    agent_tool_selection/
      golden.jsonl                       ← 15 examples: message → expected tool
      run.py
    rag/
      golden.jsonl                       ← 15 triples: question, ideal answer, ground-truth chunks
      run.py
    redteam/
      injection.jsonl                    ← Owner C populates; Owner B wires run.py
      cross_tenant.jsonl
      run.py
    redaction/
      cases.jsonl
      run.py
```

Owner B does NOT write:
- `backend/scripts/`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/lifespan.py`
- `backend/app/dependencies.py`
- `backend/app/auth/`
- `backend/app/tenancy/`
- `backend/app/routes/auth.py`
- `backend/app/routes/manager.py`
- `backend/app/routes/widget.py`
- `backend/migrations/`
- `backend/app/services/cost_meter.py`
- `backend/app/services/rate_limiter.py`
- `modelserver/`
- `guardrails/`
- `admin/`
- `widget/`
- `docker-compose.yml`

---

## Message Flow (Full Detail)

```
POST /api/v1/chat/message
        │
        ├─ Auth middleware (Owner A): verify widget JWT → extract tenant_id, session_id
        ├─ set_tenant_rls(tenant_id, session) via dependency
        │
        ├─ Guardrails input check:
        │     guardrails_client.check_input(message, tenant_id, session_id)
        │     If allowed=false → return 200 with safe refusal, log blocked attempt
        │     Use redacted_message for all downstream processing
        │
        ├─ Rate limit: check_rate_limit(tenant_id, session_id, "chat") → 429 if exceeded
        │
        ├─ Classify:
        │     classifier_client.classify(text=redacted_message, tenant_id)
        │     → { intent, confidence }
        │
        ├─ Router (workflow — router.py):
        │     spam, any confidence          → drop, return safe message, no content logged
        │     faq,     confidence >= 0.80   → RAG workflow (no agent)
        │     lead,    confidence >= 0.80   → capture_lead workflow (no agent)
        │     escalate,confidence >= 0.80   → escalate workflow (no agent)
        │     else                          → agent
        │
        ├─ [RAG workflow]
        │     Load conversation history from Redis (last 20 messages)
        │     rag.retrieve(query=redacted_message, tenant_id)
        │     Build prompt from prompts/system_agent.md + chunks + history
        │     llm_client.complete(messages=..., max_tokens=1024)
        │     record_llm_usage(tenant_id, tokens_in, tokens_out)
        │     guardrails_client.check_output(response, tenant_id, session_id)
        │     Append to Redis session memory (redacted content only)
        │     Return response
        │
        ├─ [capture_lead workflow]
        │     If lead data present: tools/capture_lead.py directly
        │     Else: llm_client single call to extract name/contact
        │     Return confirmation
        │
        ├─ [escalate workflow]
        │     tools/escalate.py directly
        │     Return escalation confirmation
        │
        └─ [agent branch — agent.py]
              Load conversation history from Redis
              Load agent_config from DB (persona, enabled_tools, max_iterations)
              Bounded tool-calling loop:
                  Build messages with system prompt + history + current message
                  llm_client.complete(messages, tools=enabled_tools, max_tokens=2048)
                  record_llm_usage(tenant_id, tokens_in, tokens_out)
                  If stop_reason == "end_turn" → break
                  If stop_reason == "tool_use" → execute tool, append result, continue
                  If max_iterations reached → return partial response
              guardrails_client.check_output(final_response, tenant_id, session_id)
              Append to Redis (redacted content)
              Return response
```

---

## Clients for External Services

### classifier_client.py

```python
async def classify(text: str, tenant_id: uuid.UUID) -> ClassifyResult:
    # POST http://modelserver:8001/classify
    # Header: Authorization: Bearer <modelserver_token>
    # On 5xx or timeout: return ClassifyResult(intent="ambiguous", confidence=0.0)
    # Fail open to agent — visitor still gets a response even if classifier is down
```

### guardrails_client.py

```python
async def check_input(message, tenant_id, session_id) -> GuardrailResult:
    # POST http://guardrails:8002/check/input
    # Header: Authorization: Bearer <guardrails_token>
    # On 5xx or timeout: FAIL CLOSED — raise GuardrailsUnavailableError
    # Caller returns safe error to visitor. Never pass through on sidecar failure.

async def check_output(message, tenant_id, session_id) -> GuardrailResult: ...
```

### embeddings_client.py

```python
async def embed(text: str) -> list[float]:
    # POST http://modelserver:8001/embed
    # Returns float vector (dimension matches the chunks table column)
    # record_embed_usage is called by rag.py after batch embedding
```

### llm_client.py

```python
async def complete(
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 1024,
    tenant_id: uuid.UUID | None = None,  # for cost recording
) -> LLMResponse:
    # Calls Anthropic Claude API
    # Reads API key from config (originally from Vault at startup)
    # Structured to make it easy to swap the provider
```

---

## Agent Implementation

`backend/app/services/agent.py`

### Tool definitions sent to the LLM

Only tools listed in `agent_config.enabled_tools` are included in the tools list sent to Claude. `tenant_id` is never in the tool input schema — the tool reads it from the FastAPI dependency, not from the LLM's tool call output.

```python
RAG_SEARCH_TOOL = {
    "name": "rag_search",
    "description": "Search the business's knowledge base for relevant information to answer the visitor's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query, max 500 chars"}
        },
        "required": ["query"]
    }
}

CAPTURE_LEAD_TOOL = {
    "name": "capture_lead",
    "description": "Record the visitor's contact information when they express interest or provide their details.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name":    {"type": "string"},
            "contact": {"type": "string", "description": "Email or phone number"},
            "intent":  {"type": "string", "description": "What the visitor is looking for"}
        },
        "required": ["name", "contact", "intent"]
    }
}

ESCALATE_TOOL = {
    "name": "escalate",
    "description": "Flag the conversation for a human when the visitor explicitly asks for one or the question is outside your knowledge.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string"}
        },
        "required": ["reason"]
    }
}
```

### Bounded loop

```python
MAX_ITERATIONS = min(agent_config.max_tool_iterations, 10)  # hard cap at 10

for iteration in range(MAX_ITERATIONS):
    response = await llm_client.complete(messages=messages, tools=active_tools, max_tokens=2048)
    await record_llm_usage(session, tenant_id, response.usage.input_tokens, response.usage.output_tokens)

    if response.stop_reason == "end_turn":
        break
    if response.stop_reason == "tool_use":
        result = await dispatch_tool(response.tool_use, tenant_id, session_id, session, redis)
        messages.append({"role": "tool", "content": result})
else:
    # Loop cap hit — likely adversarial input driving up cost
    log.warning("agent_loop_cap_hit", tenant_id=tenant_id, session_id=session_id)
    return "I wasn't able to complete your request — please try rephrasing."
```

---

## Three Agent Tools

### rag_search — `backend/app/tools/rag_search.py`

```python
async def rag_search(query: str, tenant_id: uuid.UUID, session: AsyncSession) -> dict:
    # 1. embed the query via embeddings_client.embed(query)
    # 2. pgvector ANN search — explicit WHERE tenant_id = :tid (RLS also filters)
    # 3. rerank top-10 candidates → return top-5
    # 4. record_embed_usage(session, tenant_id, approx_tokens)
```

Always uses both the explicit `WHERE tenant_id = :tid` SQL filter and the RLS policy. A future refactor that removes the SQL filter still has RLS as the backstop.

### capture_lead — `backend/app/tools/capture_lead.py`

```python
async def capture_lead(
    name: str, contact: str, intent: str,
    tenant_id: uuid.UUID,   # from FastAPI dependency — NOT from LLM tool call
    session_id: str,
    session: AsyncSession,
    redis: Redis,
) -> dict:
    # 1. validate contact: email regex OR E.164 phone regex — reject if neither
    # 2. check_rate_limit(redis, tenant_id, session_id, "capture_lead") → 429-equivalent if exceeded
    # 3. insert into leads (tenant_id from dependency, never from tool input)
    # 4. increment_rate_limit(redis, tenant_id, session_id, "capture_lead")
    # 5. return { lead_id, captured: true }
```

`tenant_id` is injected from the request context. The LLM's tool call args do not include a `tenant_id` field — there is no field in the tool schema for it. This is architectural, not a guard.

### escalate — `backend/app/tools/escalate.py`

```python
async def escalate(
    reason: str,
    conversation_id: str,
    tenant_id: uuid.UUID,   # from FastAPI dependency
    session: AsyncSession,
) -> dict:
    # insert into escalations
    # return { escalated: true, ticket_id }
```

---

## CMS Content Pipeline

### CMS CRUD (`backend/app/routes/cms.py`)

```
GET    /api/v1/cms/pages                ← list pages for tenant
POST   /api/v1/cms/pages                ← create page → trigger background index
GET    /api/v1/cms/pages/{id}           ← get one page
PUT    /api/v1/cms/pages/{id}           ← update page → trigger background re-index
DELETE /api/v1/cms/pages/{id}           ← delete page + its chunks
POST   /api/v1/cms/pages/{id}/publish   ← toggle published

GET    /api/v1/cms/agent-config         ← get tenant agent config
PUT    /api/v1/cms/agent-config         ← update agent config
```

All require `tenant_admin` role. All scoped by `get_current_tenant_id`.

**Note:** `GET /api/v1/admin/leads`, `GET /api/v1/admin/escalations`, `PATCH /api/v1/admin/escalations/{id}`, and all widget management endpoints live in `routes/tenant_admin.py`, which is **entirely owned by Owner A**. Owner B owns only `routes/cms.py`. Never add routes to `tenant_admin.py`.

### Embedding Pipeline

Triggered as a background task on page create/update. Runs in `backend/app/services/rag.py`.

```
Step 1 — Chunking
  Strategy: sentence-window chunking (512 tokens, 50-token overlap)
  Justified against naive fixed-size chunking in EVALS.md (hit@5 comparison)

Step 2 — Embedding
  embeddings_client.embed(chunk_text) → float vector
  Batched: 100 chunks per call
  record_embed_usage(session, tenant_id, tokens_per_batch) after each batch

Step 3 — Upsert into chunks table
  DELETE existing chunks WHERE page_id = :page_id AND tenant_id = :tenant_id
  INSERT new chunks with tenant_id (from dependency), page_id, chunk_index, chunk_text, embedding
```

### Retrieval

```
Step 1 — Embed query
  embeddings_client.embed(query)

Step 2 — ANN search in pgvector
  SELECT ... FROM chunks
  WHERE tenant_id = :tenant_id         ← explicit filter (belt)
  ORDER BY embedding <=> :query_vec    ← cosine distance
  LIMIT 10                             ← initial candidates

Step 3 — Rerank (the one justified improvement)
  Choice to be decided and documented in DECISIONS.md:
  Option A: cross-encoder reranker via modelserver /rerank endpoint
  Option B: query rewrite (LLM rewrites query before embedding)
  Option C: metadata filtering (filter by page section type, recency)
  Chosen option must show hit@5 improvement on the RAG golden set
  Return top-5 after rerank
```

---

## Caching Policy

Document explicitly in `docs/DECISIONS.md`. The rules:

| What | Cached? | Where | TTL | Reason |
|---|---|---|---|---|
| Conversation history | Yes | Redis | 30 min | Core feature — session memory |
| Embeddings of CMS chunks | Yes | `chunks` table (pgvector) | Until page updated | Expensive to recompute; content rarely changes |
| Embeddings of queries | **No** | — | — | Queries are unique; caching them provides no benefit and stores visitor input |
| Retrieval results | **No** | — | — | Tenant content can be updated; stale results mislead the agent |
| LLM responses | **No** | — | — | Each turn depends on conversation history — safe caching requires hashing the full context, not just the current message |
| Agent config (persona, tools) | Yes | In-memory per process | Until restart | Low-traffic data, fine to re-fetch on restart |
| Tenant rails (guardrails sidecar) | Yes | In-memory in sidecar | 60 seconds | Fetched from backend; brief staleness acceptable |

Document the above table verbatim in `docs/DECISIONS.md` with the rationale. Reviewers grade this document.

---

## Router Efficiency Metric

The hybrid router's value is measured by how often it keeps turns **off** the agent. Track and report:

```python
# In router.py — emit a structured log event for every turn
log.info("turn_routed",
    tenant_id=str(tenant_id),
    session_id=session_id,
    intent=intent,
    confidence=confidence,
    routed_to="workflow" | "agent",   # "workflow" = spam/faq/lead/escalate branch
)
```

Aggregate in `docs/EVALS.md`:
- Total turns per route: spam, faq, lead, escalate, agent
- % turns handled without the agent = (spam + faq + lead + escalate) / total
- Estimated cost saving: (agent turns avoided) × (avg LLM tokens per agent turn) × token price
- Report separately for Tenant A and Tenant B seeded data

The brief requires you to measure this and report what fraction of turns stay off the agent and what that saves per tenant.

---

## Redis Session Memory

Key pattern (frozen in INTERFACES.md): `conversation:{tenant_id}:{session_id}`

```python
# backend/app/services/ — or inline in chat route
async def get_history(redis, tenant_id, session_id, max_messages=20) -> list[dict]:
    raw = await redis.lrange(f"conversation:{tenant_id}:{session_id}", 0, max_messages - 1)
    return [json.loads(r) for r in raw]

async def append_message(redis, tenant_id, session_id, role, content_redacted) -> None:
    entry = json.dumps({"role": role, "content": content_redacted, "timestamp": ...})
    key = f"conversation:{tenant_id}:{session_id}"
    await redis.lpush(key, entry)
    await redis.ltrim(key, 0, 19)   # keep last 20
    await redis.expire(key, 1800)   # 30-min TTL refreshed on every write
```

Content stored is the guardrails-redacted version — no raw PII or secrets ever written to Redis.

---

## Prompts

`prompts/` at project root — version-controlled.

```
prompts/
  system_agent.md                ← agent system prompt
    Template vars: {persona_name}, {persona_description}, {tenant_name}

  router_classifier.md           ← describes how classifier outputs map to actions
                                    (documentation for devs, not injected into LLM)

  tenant_persona_template.md     ← the block injected into system_agent.md at runtime
    Template vars: {persona_name}, {persona_description}
```

Prompts loaded from disk at request time with an in-memory cache per process (no hot-reload). A prompt change requires a deployment — intentional so changes are tracked in git.

---

## Eval Golden Sets

### Agent Tool Selection — `backend/evals/agent_tool_selection/golden.jsonl`

```jsonl
{"id": "ts-001", "message": "What are your business hours?", "expected_tool": "rag_search", "should_not_use": ["capture_lead", "escalate"]}
{"id": "ts-002", "message": "I'd like a quote — my email is john@example.com", "expected_tool": "capture_lead", "should_not_use": ["escalate"]}
{"id": "ts-003", "message": "I need to speak with a human right now", "expected_tool": "escalate", "should_not_use": ["capture_lead"]}
{"id": "ts-004", "message": "What's your return policy and can you take down my contact info?", "expected_tools": ["rag_search", "capture_lead"], "note": "multi-tool turn — must reach agent"}
```

15 examples total. Threshold in `eval_thresholds.yaml`: `agent_tool_accuracy: 0.80` (12/15 correct).

### RAG Golden Set — `backend/evals/rag/golden.jsonl`

```jsonl
{"id": "rag-001", "question": "What is the return policy?", "ideal_answer": "Returns accepted within 30 days with receipt.", "ground_truth_chunks": ["acme-page-001-chunk-3"], "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
```

15 triples. Metrics: hit@5, MRR, faithfulness, answer_relevancy.
Thresholds: `rag_hit_at_5: 0.75`, `rag_faithfulness: 0.70`.

**Judge agreement requirement (from the brief):** For faithfulness and answer_relevancy scores, the eval runner uses an LLM judge (Claude call) to score each answer. Owner B must hand-label at least 10 of the 15 examples manually and measure the agreement between their labels and the LLM judge's labels. Report in `docs/EVALS.md`:
- Per-example: human label vs judge label, agree/disagree
- Cohen's kappa or simple % agreement
- If agreement < 0.7: re-examine the judge prompt and document what was changed

This is required, not optional. Thresholds cannot be set with confidence until judge agreement is validated.

---

## What Owner B Depends On

| Dependency | From | When |
|---|---|---|
| `get_current_tenant_id` dependency | Owner A | Day 1 — cannot write a scoped DB query without it |
| Seeded tenants | Owner A | Day 1 |
| `POST /classify` stub (returns `ambiguous`) | Owner C | Day 1 — router cannot function without it |
| `POST /check/input` stub (returns `allowed: true`) | Owner C | Day 1 |
| `cost_meter.py` functions | Owner A | Day 1 |
| `rate_limiter.py` functions | Owner A | Day 1 |

---

## What Owner B Delivers That Others Depend On

| Deliverable | Used by | When |
|---|---|---|
| Tool schemas (in INTERFACES.md) | Owner C (guardrails payload validation) | Day 1 — before code |
| `POST /api/v1/chat/message` | Owner D (widget) | Day 2 |
| CMS endpoints | Owner D (admin UI) | Day 2 |
| Eval golden sets | Owner D (CI gates) | Day 3 |

---

## Day 1 Checklist

- [ ] Tool schemas committed to `specs/shared/contracts/INTERFACES.md`
- [ ] `backend/app/routes/chat.py` — real router with placeholder response (replaces A's stub)
- [ ] `backend/app/routes/cms.py` — at minimum, POST /api/v1/cms/pages stub
- [ ] `classifier_client.py` — calls the stub model server, handles unavailability gracefully
- [ ] `guardrails_client.py` — calls the stub sidecar, fails closed on 5xx
- [ ] Session memory read/write working against Redis
- [ ] At least one CMS page seeded for Tenant A (so RAG has something to retrieve)

---

## Edge Cases

**Classifier unavailable:** Route as `ambiguous` (agent). Log the failure. Visitor still gets a response.

**Guardrails unavailable:** Fail closed. Safe error to visitor. Never skip the check.

**Agent loop cap hit:** Return a polite partial response. Log the cap hit — it may indicate adversarial input.

**`capture_lead` cross-tenant write attempt:** `tenant_id` comes from the FastAPI dependency. The LLM's tool call args have no `tenant_id` field. There is nothing for a prompt injection to override.

**RAG retrieving another tenant's chunks:** Cannot happen if both the explicit `WHERE tenant_id = :tid` filter and the RLS policy are in place. Owner B writes an integration test: query for Tenant A content using Tenant B's session — assert zero results.

**Large page re-indexing:** Background task. The CMS edit endpoint returns 202 immediately. Old chunks remain searchable until the new ones are committed.
