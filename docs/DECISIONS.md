# Decisions

## Owner C — Classifier deployment choice

Decision: deploy the classical TF-IDF + logistic regression router from `modelserver/artifacts/classical_model.joblib`.

Why this ships:

- It preserved strong public-test performance (`macro_f1=0.9836`) while producing zero wrong direct routes on both the threshold-selection set and the final product golden set.
- The DL ONNX baseline scored slightly higher on the public test set, but it produced high-confidence wrong direct routes (`2` on public test, `3` on final product golden), which is the more dangerous failure mode for direct routing.
- The classical artifact keeps the serving runtime lean: `sklearn + joblib`, with no `torch`, `transformers`, or `sentence-transformers` in the modelserver container.

Operational consequence:

- The deployed model remains `classical`.
- The DL ONNX artifact stays in-repo as a documented comparison baseline, not as the default serving path.
- `onnxruntime` is included in `modelserver/pyproject.toml` to support the exported DL ONNX baseline and future switchability, while the deployed runtime path remains classical.
- The runtime serving threshold is `0.80`. The exported `0.75` threshold is kept only as Colab experiment provenance and does not control modelserver behavior.
- `/embed` remains a 768-zero contract stub because no BGE ONNX artifact was present in the export; it must not be treated as production retrieval quality.

## Owner B — Agent-vs-workflow routing rationale

Decision: route high-confidence intents (≥ 0.80) directly to single-shot workflows; everything else falls through to the bounded agent loop.

**Why not always use the agent?**

- The full agent loop can consume up to 10 tool iterations per turn. At ~$0.003/1K input tokens, a 5-turn agent call over a 4K-token context costs roughly $0.06–$0.12 per message. A direct FAQ workflow costs one embed call + one LLM call with a context typically under 2K tokens — approximately 70–80% cheaper per turn.
- Deterministic workflows (FAQ/lead/escalate) have zero tool-loop variance: they always make exactly one LLM call and at most one tool call. The agent loop makes the billing envelope hard to predict.
- High-confidence faq/lead/escalate are the most common turn types in a concierge widget (typically 60–75% of traffic). Routing these cheaply has outsized cost impact.

**Why 0.80 as the confidence gate?**

The classifier ships at `macro_f1 = 0.98` on the public test set, but accuracy on ambiguous edge cases is lower. At confidence < 0.80 the classifier is signalling uncertainty — the agent loop's ability to seek clarification is more valuable than the cost saving. Empirically, setting the gate at 0.80 leaves ~20–30% of turns to the agent while capturing the long tail of ambiguous inputs safely.

**Bounded agent loop cap**

`MAX_ITERATIONS = min(config.max_tool_iterations, 10)`. The hard cap of 10 prevents runaway tool loops from a misconfigured tenant. In practice tenant configs ship with `max_tool_iterations = 5`.

---

## Owner B — Chunking strategy

Decision: sentence-window chunker, 512-token window (~2048 chars), 50-token overlap (~200 chars), sentence-boundary breaks.

**Why sentence-window over fixed-size?**

- Fixed character splits can cut mid-sentence, producing chunks whose first and last sentences are syntactically incomplete. Embedding quality degrades when the chunk boundary lands inside a sentence because the embedding model sees a fragment that doesn't form a coherent semantic unit.
- Sentence-window chunking uses `rfind(". ")` to walk back to the nearest sentence boundary inside the latter half of each window, so every chunk starts and ends at a natural prose boundary.

**Why 512 tokens / 50-token overlap?**

- 512 tokens is the canonical sweet spot for BGE-style embedding models (the modelserver contract in INTERFACES.md). Longer inputs exceed the optimal context window for dense retrieval; shorter inputs lose enough context that embedding similarity degrades.
- 50-token overlap (≈10% of window) prevents facts that straddle a chunk boundary from being fully absent from both chunks. The overlap is intentionally small to avoid double-counting in cost and to keep the ANN index lean.

---

## Owner B — Retrieval rerank choice

Decision: per-page diversity rerank (cap 2 chunks per source page, return top-5 from a pool of 20). No cross-encoder reranker.

**Why no cross-encoder?**

- Cross-encoder rerankers add a second model inference call per retrieved chunk, which would multiply latency (roughly 20 calls for a pool of 20) and require a second modelserver endpoint that is not in the current INTERFACES.md contract.
- For a single-tenant knowledge base with O(10²) pages, ANN cosine distance on good embeddings already achieves strong precision. A cross-encoder is reserved for when the knowledge base grows to O(10⁴)+ chunks and cosine distance starts to plateau.

**Why diversity rerank?**

Without the per-page cap, naive ANN over a dense FAQ page can return all 5 top-k results from the same page, starving the result set of topical breadth. A user asking about business hours who also has a delivery question gets better coverage if at most 2 chunks come from the business-hours page.

---

## Owner B — Session memory and caching policy

| Layer | What is cached | TTL | Invalidation |
|---|---|---|---|
| Redis session history | Last 20 messages per session (LPUSH + LTRIM 0 19) | 30 min (EXPIRE 1800) | Automatic on TTL expiry; overwritten on new session |
| RAG chunk table | Chunks persist until the CMS page is updated or unpublished | Permanent (DB) | `index_page()` deletes all chunks for the page before re-inserting |
| Agent config | Loaded from DB on every request via `AgentConfig` repository | None (no app-level cache) | Immediate — admin changes take effect on the next request |
| Embedding vectors | Stored in pgvector `chunks.embedding` column | Permanent (DB) | Replaced on page re-index |
| Guardrails response | Not cached — every message checked fresh | — | — |
| Classifier response | Not cached — called per turn | — | — |

**Why no agent-config cache?**

Tenant admins expect persona and tool configuration changes to take effect immediately. A cache would introduce a window where a misconfigured or inappropriate persona is served despite the admin having corrected it. The DB round-trip is cheap relative to the LLM call that follows.

---

## Owner C — Guardrails image size deviation

Decision: ship the guardrails sidecar image at ~618 MB, 18 MB over the documented 600 MB target.

Why this deviates:

- The spec targets `< 600 MB` for the guardrails container. Our build lands at ~618 MB on disk.
- The bulk comes from Presidio's hard dependency on spaCy (~109 MB) plus `blis`, `numpy`, and `phonenumbers` country metadata (~80 MB combined). These are required transitively by `presidio-analyzer`, which the spec mandates for PII detection.
- The image already excludes `torch`, `transformers`, and `sentence-transformers` (verified with `pip show`). The multi-stage build uses a bind-mount for build wheels so no compiler or wheel cache layer persists in the runtime image.
- Aggressive pruning (stripping spaCy internals, removing `pip`/`setuptools`) could close the 18 MB gap but risks breaking PERSON detection and in-container test workflows. The risk was judged not worth the marginal size win.

Operational consequence:

- The 18 MB overage is documented here rather than silently shipped. If the cap becomes a hard CI gate, the next step is to drop Presidio entirely and rely on regex-only PII redaction (the test suite and red-team probes already pass via the regex path).
- All other guardrails constraints are met: red-team block rate = 1.0 (12/12 probes), no forbidden deps, no runtime network fetches, sub-3-second test suite.

---

## Owner C — LLM zero-shot baseline result

Decision: record the LLM zero-shot baseline (claude-haiku-4-5) in `modelserver/model_card.yaml` as a measured comparison point, using the `strict` prompt variant as the selected LLM baseline. Never deploy it.

Why classical still ships after prompt optimization:

- The best LLM prompt variant (`strict`) reached `macro_f1 = 0.6257`, still far below the shipped classical router at `macro_f1 = 0.9836`.
- The classical router is deterministic and local. It requires no outbound API call, has near-zero marginal cost per request, and avoids dependence on external model availability.
- The strict LLM baseline costs about `$0.089171` for 150 routes, roughly `$0.59` per 1000 routing calls, while the classical router serves at effectively `$0` marginal cost.
- The strict LLM baseline averages `1391.67 ms` per row versus classical at about `0.18 ms` per row, so the LLM path is orders of magnitude slower.
- Fewshot improved `unknown_or_agent` handling (`0.4828` F1) but damaged `lead` performance (`0.2727` F1), which is not acceptable for a concierge router that must protect lead capture quality.
- The classical model preserved the safer direct-route behavior that matters most operationally: zero wrong direct routes on both the threshold-selection set and the final product golden set. The DL baseline missed that bar, and the LLM baseline remains too weak and too expensive to justify replacing a safer local router.

The LLM baseline artifacts live under `artifacts/classifier/llm_baseline*` for reproducibility but are never loaded by the modelserver.

---

## Owner C — Embedding model swap (BGE → OpenAI)

Decision: serve `/embed` from OpenAI `text-embedding-3-small` with `dimensions=768`, instead of exporting BGE-small-en-v1.5 to ONNX.

Why we swapped:

- The original plan was to export BGE-small to ONNX in a Colab notebook and serve it via `onnxruntime` in the modelserver. That requires committing a ~130 MB ONNX artifact plus a tokenizer, and ships a local model the team must maintain.
- A hosted embedder removes that maintenance burden entirely: no artifact to keep SHA-pinned, no tokenizer to ship, no ONNX session to manage. The modelserver stays lean and the demo path stays reproducible from any machine.
- OpenAI `text-embedding-3-small` supports `dimensions=N` (256, 512, 768, 1024, 1536). We request 768 so the response **exactly matches the existing frozen contract**: `chunks.embedding vector(768)` in Postgres, the `vector_dim: 768` field in `INTERFACES.md`, and the 768-zero shape that Owner B's `embeddings_client.py` already consumes. No schema migration, no cross-owner coordination required.
- Cost is negligible at bootcamp scale: $0.02 per 1M tokens. Indexing 100 CMS pages × 500 tokens × 2 chunks/page costs ~$0.002.

Why not Anthropic, why not Voyage:

- Anthropic does not offer an embeddings API; their docs recommend Voyage.
- Voyage `voyage-3-lite` is 512 dim and `voyage-3` is 1024 dim. Neither produces 768-dim vectors, so picking Voyage would force a Postgres column migration and Owner B + Owner A coordination — not worth the friction.

Operational consequence:

- `modelserver/app.py` reads the OpenAI key from Vault at `secret/embed/api_key`, with env-var fallback `OPENAI_API_KEY` for local dev.
- The OpenAI SDK is added to `modelserver/pyproject.toml` and `modelserver/Dockerfile`.
- `/embed` returns HTTP 503 (`EMBEDDER_UNAVAILABLE`) if no API key is configured at startup. Upstream OpenAI errors propagate as HTTP 502 (`EMBEDDER_UPSTREAM_ERROR`).
- `model_card.yaml` `embedding.status` is updated from `pending` to `deployed` with provider, vector_dim, and the Vault secret path documented.
- No artifact SHA is recorded for the embedder because nothing is shipped locally — the hosted model is the source of truth.

---

## Owner C — Classifier artifact commit policy

Decision: commit the small SHA-pinned classifier artifacts required by the modelserver for bootcamp reproducibility and fresh-clone demo readiness.

The original Owner C spec assumed artifacts would be mounted or ignored. For this repo branch, the exception is intentional: `classical_model.joblib`, the exported DL ONNX baseline, and their small auxiliary runtime artifacts remain committed with hashes recorded in `modelserver/model_card.yaml`.

Raw datasets, Colab export folders, caches, zip files, notebooks caches, secrets, and large/generated artifacts remain ignored and must not be committed.
