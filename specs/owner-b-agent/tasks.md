# Owner B — Task List

Format: `[ID] [P?] Description — file`
`[P]` = can run in parallel with other `[P]` tasks in the same phase.

**Blocked on Owner A Day-1 gate and Owner C Day-1 stubs before any code can run end-to-end.**

---

## Phase 0 — Contracts (Day 1, before any code)

- [ ] B-001 Commit final tool schemas to `specs/shared/contracts/INTERFACES.md` — confirm `tenant_id` absent from LLM-facing schemas for all three tools — `specs/shared/contracts/INTERFACES.md`

---

## Phase 1 — Service Clients (Day 1 — all parallel, depend only on B-001 and Owner A/C Day-1 gates)

- [ ] B-002 [P] Write `classifier_client.py` — `classify(text, tenant_id) -> ClassifyResult`; on 5xx return `ClassifyResult(intent="ambiguous", confidence=0.0)` (fail open) — `backend/app/services/classifier_client.py`
- [ ] B-003 [P] Write `guardrails_client.py` — `check_input()` + `check_output()`; on 5xx raise `GuardrailsUnavailableError` (fail closed) — `backend/app/services/guardrails_client.py`
- [ ] B-004 [P] Write `embeddings_client.py` — `embed(text) -> list[float]`; calls `POST /embed` on modelserver — `backend/app/services/embeddings_client.py`
- [ ] B-005 [P] Write `llm_client.py` — `complete(messages, tools, max_tokens, tenant_id) -> LLMResponse`; Anthropic SDK adapter — `backend/app/services/llm_client.py`

---

## Phase 2 — Session Memory & Basic Route (Day 1)

- [ ] B-006 Write Redis session memory helpers — `get_history()` + `append_message()` with LPUSH + LTRIM 0 19 + EXPIRE 1800 — inline in chat service or `backend/app/services/`
- [ ] B-007 Write `backend/app/routes/chat.py` — replace A's 501 stub; minimal version: guardrails input check → rate limit → classify → return placeholder response (agent not wired yet) — `backend/app/routes/chat.py`
- [ ] B-008 Write `backend/app/routes/cms.py` — replace A's 501 stub; at minimum `POST /api/v1/cms/pages` so Owner D can seed content — `backend/app/routes/cms.py`

---

## Phase 3 — Router & Workflows (Day 2)

- [ ] B-009 Write `backend/app/services/router.py` — full classifier-driven router: spam drop, faq→RAG workflow, lead→capture_lead workflow, escalate→escalate workflow, ambiguous/low-confidence→agent — `backend/app/services/router.py`
- [ ] B-010 [P] Write `backend/app/services/rag.py` — chunking (sentence-window 512t/50t overlap) + embed + pgvector ANN + rerank → top-5 — `backend/app/services/rag.py`
- [ ] B-011 [P] Write `backend/app/repositories/chunk_repo.py` — tenant-filtered pgvector ANN query with explicit `WHERE tenant_id = :tid` — `backend/app/repositories/chunk_repo.py`
- [ ] B-012 [P] Write `backend/app/repositories/cms_page_repo.py` — CRUD + publish toggle — `backend/app/repositories/cms_page_repo.py`
- [ ] B-013 [P] Write `backend/app/repositories/lead_repo.py` — insert + paginated list — `backend/app/repositories/lead_repo.py`
- [ ] B-014 [P] Write `backend/app/repositories/escalation_repo.py` — insert + status update — `backend/app/repositories/escalation_repo.py`

---

## Phase 4 — Agent & Tools (Day 2)

- [ ] B-015 Write `backend/app/services/agent.py` — bounded loop: `MAX_ITERATIONS = min(config.max_tool_iterations, 10)`; load history + config; dispatch tools; guardrails output check; append to Redis — `backend/app/services/agent.py`
- [ ] B-016 [P] Write `backend/app/tools/rag_search.py` — `rag_search(query, tenant_id, session)`: embed → ANN (WHERE tenant_id=:tid) → rerank → top-5; call `record_embed_usage` — `backend/app/tools/rag_search.py`
- [ ] B-017 [P] Write `backend/app/tools/capture_lead.py` — validate contact (email OR E.164); check rate limit; insert lead with `tenant_id` from dependency; increment rate limit — `backend/app/tools/capture_lead.py`
- [ ] B-018 [P] Write `backend/app/tools/escalate.py` — insert escalation with `tenant_id` from dependency; return `{escalated: true, ticket_id}` — `backend/app/tools/escalate.py`
- [ ] B-019 Wire full `chat.py` route — replace placeholder from B-007 with complete flow: guardrails → rate limit → classify → router → workflow or agent → guardrails output → Redis → return — `backend/app/routes/chat.py`

---

## Phase 5 — CMS Pipeline & Embedding (Day 2)

- [ ] B-020 Complete `backend/app/routes/cms.py` — all 9 endpoints (pages CRUD + publish, agent-config get/put); background task triggers re-indexing on create/update — `backend/app/routes/cms.py`
- [ ] B-021 Embedding pipeline in `rag.py` — chunking → batch embed (100 per call) → delete old chunks → insert new with `record_embed_usage` — `backend/app/services/rag.py`
- [ ] B-022 Write `backend/evals/rag/seed.py` — seeds CMS pages for Tenant A so RAG eval has content to retrieve — `backend/evals/rag/seed.py`

---

## Phase 6 — Prompts (Day 2, parallel)

- [ ] B-023 [P] Write `prompts/system_agent.md` — agent system prompt with `{persona_name}`, `{persona_description}`, `{tenant_name}` template vars — `prompts/system_agent.md`
- [ ] B-024 [P] Write `prompts/router_classifier.md` — developer reference: how classifier labels map to route actions — `prompts/router_classifier.md`
- [ ] B-025 [P] Write `prompts/tenant_persona_template.md` — the persona block injected into system prompt at runtime — `prompts/tenant_persona_template.md`

---

## Phase 7 — Eval Golden Sets (Day 3)

- [ ] B-026 [P] Write 15 agent tool-selection examples — `backend/evals/agent_tool_selection/golden.jsonl`
- [ ] B-027 [P] Write `backend/evals/agent_tool_selection/run.py` — sends each example to `/chat/message`, checks tool used vs expected — `backend/evals/agent_tool_selection/run.py`
- [ ] B-028 [P] Write 15 RAG triples (question, ideal answer, ground-truth chunk IDs) for Tenant A — `backend/evals/rag/golden.jsonl`
- [ ] B-029 [P] Write `backend/evals/rag/run.py` — computes hit@5, MRR, faithfulness (LLM judge), answer_relevancy — `backend/evals/rag/run.py`
- [ ] B-030 [P] Write `backend/evals/classifier/golden.jsonl` — held-out test examples for classifier eval — `backend/evals/classifier/golden.jsonl`
- [ ] B-031 [P] Write `backend/evals/classifier/run.py` — calls `/classify`, computes macro-F1 + per-class F1, compares to thresholds — `backend/evals/classifier/run.py`
- [ ] B-032 [P] Wire `backend/evals/redteam/run.py` — sends Owner C's injection.jsonl probes through `/chat/message`, asserts all blocked — `backend/evals/redteam/run.py`
- [ ] B-033 [P] Wire `backend/evals/redaction/run.py` — sends cases.jsonl through `/chat/message`, checks response AND logs for raw PII/secrets — `backend/evals/redaction/run.py`

---

## Phase 8 — Router Efficiency Metric (Day 3)

- [ ] B-034 Add structured log event to `router.py` for every turn: `tenant_id`, `intent`, `confidence`, `routed_to: "workflow"|"agent"` — `backend/app/services/router.py`
- [ ] B-035 Aggregate metrics: % turns off agent, estimated cost saving per tenant — document in `docs/EVALS.md`

---

## Phase 9 — Judge Agreement & Documentation (Day 3 / Demo Prep)

- [ ] B-036 Hand-label at least 10 of 15 RAG golden examples (faithfulness + answer_relevancy); compute agreement with LLM judge (Cohen's kappa or %); document in `docs/EVALS.md`
- [ ] B-037 Write `docs/DECISIONS.md` — agent-vs-workflow rationale, chunking strategy, rerank choice, caching policy table — `docs/DECISIONS.md`
- [ ] B-038 Write `docs/EVALS.md` sections for: RAG eval methodology, judge agreement, router efficiency, agent tool-selection gate — `docs/EVALS.md`

---

## Day 1 Completion Checklist (Gate)

- [ ] Tool schemas in `INTERFACES.md` — `tenant_id` absent from all LLM-facing schemas
- [ ] `chat.py` stub live (guardrails + classify + placeholder response)
- [ ] `cms.py` stub live (at least POST /pages)
- [ ] `classifier_client.py` calls stub modelserver, handles 5xx gracefully
- [ ] `guardrails_client.py` calls stub sidecar, fails closed on 5xx
- [ ] Redis session memory read/write working
- [ ] At least one CMS page seeded for Tenant A
