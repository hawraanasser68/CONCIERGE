# Owner B — Implementation Plan
## Agent, RAG & Memory

---

## Summary

Owner B builds everything between the message arriving at the API and the response leaving it: the classifier-driven hybrid router, the bounded tool-calling agent, three tools, the RAG pipeline, Redis session memory, all external service clients, and the CMS content pipeline. The core design principle is to keep as many turns as possible off the expensive agent path — only truly ambiguous messages should reach Claude.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| LLM | Anthropic Claude (claude-sonnet-4-5 or latest) | Tool use, structured output, reliable instruction following |
| LLM client | `anthropic` Python SDK | Native tool use support |
| Embeddings | modelserver `/embed` (BGE-small ONNX) | Zero marginal cost, no external API call for embeddings |
| Vector search | pgvector + asyncpg | Already in the DB, no extra infra |
| Session memory | Redis (aioredis) | Fast, TTL-native, already in docker-compose |
| HTTP clients | httpx (async) | Calls modelserver + guardrails |
| Chunking | sentence-window, 512 tokens, 50-token overlap | Balance between context and precision |
| Dependency management | uv | Shared pyproject.toml in backend/ |

---

## Architecture Decisions

### Classifier-Driven Hybrid Router
The classifier result gates whether the agent is invoked at all. Four intent labels (spam, faq, lead, escalate) route to cheap deterministic workflows. Only `ambiguous` (or low-confidence results < 0.80) routes to the agent. This keeps the majority of turns off the LLM call path entirely.

**Why not always use the agent?**
Every agent turn costs at minimum 1 LLM call (often 2-3 with tool calls). A FAQ answer via RAG costs 1 embed + 1 LLM call but with a much shorter context window. Spam costs nothing. The classifier saves cost and latency on the most common traffic patterns.

### Bounded Tool Loop
Hard cap at `min(agent_config.max_tool_iterations, 10)`. An unbounded loop is a cost and DoS vector — adversarial input can drive the agent to call tools indefinitely. Hitting the cap returns a polite partial response and logs a warning.

### Tenant Isolation in Tools
`tenant_id` is injected from the FastAPI dependency (`get_current_tenant_id`), not from the LLM's tool call output. The LLM-facing tool schema has no `tenant_id` field. This is architectural, not a guard — there is nothing for a prompt injection to override.

### Caching Policy
- **Cache:** chunk embeddings (in pgvector), conversation history (Redis 30min), agent config (in-memory per process)
- **Do not cache:** query embeddings, retrieval results, LLM responses
- Full rationale in `docs/DECISIONS.md`

### RAG Improvement
One justified rerank strategy beyond naive ANN. Chosen approach documented with hit@5 comparison in `docs/DECISIONS.md`.

### Guardrails Fail Closed / Classifier Fails Open
If guardrails sidecar is unavailable → block the message (safe refusal to user). If classifier is unavailable → route as `ambiguous` (agent handles it). Rationale: a guardrails failure is a security failure; a classifier failure is a degraded experience.

---

## Key Constraints

- `tenant_id` never in LLM-facing tool schemas
- Redis stores redacted content only (guardrails-cleaned, never raw PII)
- Max 20 messages per Redis key; 30-min TTL refreshed on every write
- Conversation history loaded for ALL branches (RAG, lead, escalate, agent) — not just agent
- % turns off agent must be measured and reported in `docs/EVALS.md`
- Judge agreement (human vs LLM judge) must be measured for RAG faithfulness scores

---

## Dependencies on Other Owners

| Needs | From | When |
|---|---|---|
| `get_current_tenant_id` dependency | Owner A | Day 1 — cannot write any scoped query |
| `cost_meter.py` and `rate_limiter.py` | Owner A | Day 1 |
| `agent_config_repo.py` | Owner A | Day 1 |
| `POST /classify` stub | Owner C | Day 1 — router blocked without it |
| `POST /check/input` + `/check/output` stubs | Owner C | Day 1 |
| `POST /embed` stub | Owner C | Day 1 — chunking pipeline needs embeddings |
| Seeded tenants | Owner A | Day 1 — golden sets reference aaaa..., bbbb... |
