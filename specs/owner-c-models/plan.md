# Owner C — Implementation Plan
## Models, Security & Guardrails

---

## Summary

Owner C owns two separate services (modelserver and guardrails sidecar) plus cross-cutting security infrastructure in the backend. The Day-1 priority is getting both services to return valid stub responses so Owner B's router is unblocked. The real classifier and rails come in Days 2-3.

---

## Tech Stack

### modelserver
| Layer | Choice | Reason |
|---|---|---|
| Framework | FastAPI + uvicorn | Consistent with backend |
| Classical model | scikit-learn (TF-IDF + LR) | Fast, ~$0 serving cost, interpretable |
| DL model | onnxruntime | No torch in container — ONNX export done offline |
| Embeddings | OpenAI `text-embedding-3-small` (hosted, `dimensions=768`) | No local model artifact to ship; same 768-dim contract as original BGE plan; see docs/DECISIONS.md |
| Vault client | hvac | Service token at startup |
| Dependency management | uv | Per-service pyproject.toml |
| **Image size target** | **< 500MB** | Hard constraint from brief |

### guardrails
| Layer | Choice | Reason |
|---|---|---|
| Framework | FastAPI + NeMo Guardrails | NeMo handles Colang rail execution |
| PII detection | Presidio | Named entity recognition for PII |
| Vault client | hvac | Service token at startup |
| **Image size target** | **< 600MB** | Hard constraint from brief |

### Training (offline — never shipped)
| Step | Tool |
|---|---|
| Classical training | scikit-learn in Jupyter notebook |
| DL training | PyTorch / Keras in Jupyter notebook |
| DL → ONNX export | `torch.onnx.export` |
| BGE → ONNX export | ~~`torch.onnx.export`~~ — superseded; using hosted OpenAI embedder instead (see docs/DECISIONS.md) |
| Classical → joblib | `joblib.dump` |

---

## Architecture Decisions

### Why three classifier approaches?
The brief requires comparison. Classical (LR) is the likely winner: $0 serving cost, sub-1ms p50, good enough macro-F1. DL ONNX adds ~2-5ms p50 for marginal F1 gain that doesn't justify the added complexity. LLM zero-shot is measured only — never deployed. Rationale in model_card.yaml.

### Why no torch in any container?
torch adds ~1.5GB to an image. The model artifacts (ONNX, joblib) are produced offline in notebooks and mounted/copied into the container. onnxruntime is a ~50MB inference-only runtime.

### SHA-256 enforcement
modelserver reads model_card.yaml at startup, computes SHA-256 of every loaded artifact, and compares to the committed hash. Mismatch → `exit(1)`. A tampered or accidentally overwritten artifact never silently serves wrong predictions.

### Guardrails Fail Closed
If the guardrails sidecar is unreachable (5xx or timeout), Owner B's `guardrails_client.py` must block the message. This means a sidecar outage blocks all chat — intentional. A guardrails failure is a security failure, not a degraded experience.

### Platform Rails (Locked)
Injection, jailbreak, cross-tenant probe, PII redaction — these run on every message regardless of tenant configuration. Applied before tenant rails. Tenant config cannot disable or weaken them.

### Tenant Rails (Configurable)
Applied after platform rails. Loaded from `GET /api/v1/admin/agent-config`, cached 60 seconds per tenant. On fetch failure: apply platform rails only. Tenant rails can only restrict further — they cannot open up what platform rails blocked.

### Per-Class F1 Requirement
Macro-F1 alone is insufficient. A model with 0.95 macro-F1 but 0.3 spam F1 would let spam through the router. CI gate requires per-class F1 for every deployed label.

---

## Key Constraints

- No torch, no transformers, no sentence-transformers in any container
- modelserver < 500MB image; guardrails < 600MB image
- SHA-256 enforcement: startup failure if artifact hash mismatches model_card.yaml
- Logs: timestamp, tenant_id, intent, confidence, latency — never message content
- Tracing spans: tenant_id, session_id, token counts, latencies — never message content or PII
- Red-team block rate: 1.0 (100%) — every probe must be blocked

---

## Dependencies on Other Owners

| Needs | From | When |
|---|---|---|
| Vault setup + all secret paths seeded | Owner A | Day 1 — service tokens must be readable |
| Tool schemas in INTERFACES.md | Owner B | Day 1 — guardrails validates tool call payloads |
| Seeded tenant UUIDs (aaaa..., bbbb...) | Owner A | Day 1 — red-team probes reference these |
| `backend/app/tracing.py` stub | Owner A | Day 1 — C fills real spans into A's stub |
