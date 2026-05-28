# Owner C — Task List

Format: `[ID] [P?] Description — file`
`[P]` = can run in parallel with other `[P]` tasks in the same phase.

**Day-1 stubs are the critical path — Owner B's entire router is blocked until these are live.**

---

## Phase 0 — Day-1 Stubs (Day 1, strict order)

- [ ] C-001 Write `modelserver/app.py` stub — three endpoints: `GET /health` → 200, `POST /classify` → `{"intent": "ambiguous", "confidence": 0.5}`, `POST /embed` → `{"embedding": [0.0, ..., 0.0]}` (768 zeros); service token validation from Vault on all non-health endpoints — `modelserver/app.py`
- [ ] C-002 Write `modelserver/Dockerfile` — `FROM python:3.11-slim`; deps: fastapi, uvicorn, hvac, numpy; target < 500MB — `modelserver/Dockerfile`
- [ ] C-003 Write `modelserver/pyproject.toml` — minimal deps for stub (no onnxruntime yet) — `modelserver/pyproject.toml`
- [ ] C-004 Write `guardrails/server.py` stub — `GET /health` → 200, `POST /check/input` → `{"allowed": true, "flagged_categories": [], "redacted_message": "<input>"}`, `POST /check/output` → same; service token validation from Vault — `guardrails/server.py`
- [ ] C-005 Write `guardrails/Dockerfile` — `FROM python:3.11-slim`; stub deps only — `guardrails/Dockerfile`
- [ ] C-006 Verify both stubs pass Owner A's Day-1 smoke test: `GET /health` → 200 on ports 8001 and 8002; requests without Bearer token → 401
- [ ] C-007 Write `backend/app/services/redaction.py` — regex patterns (sk-, Bearer, ghp_, AKIA) + Presidio PII; `redact(text: str) -> str` — `backend/app/services/redaction.py`

---

## Phase 1 — Offline Training (Day 2, all parallel — done in notebooks, not in containers)

- [ ] C-008 [P] Choose and download labeled intent dataset (CLINC150, Banking77, or custom 500+); record name + URL + SHA-256 in `model_card.yaml` — `modelserver/model_card.yaml`
- [ ] C-009 [P] Train classical classifier in `train_classifier_classical.ipynb` — TF-IDF (ngram 1-2, 50k features) + LR (max_iter=1000); 80/20 split seed=42; record macro-F1 + per-class F1 + p50/p99 latency — `modelserver/notebooks/train_classifier_classical.ipynb`
- [ ] C-010 [P] Export classical model to joblib — `joblib.dump(pipeline, "artifacts/classical_model.joblib")`; compute SHA-256 — `modelserver/artifacts/`
- [ ] C-011 [P] Train DL model in `train_classifier_dl_onnx.ipynb` — DistilBERT fine-tuned or MLP over frozen embeddings; export to ONNX — `modelserver/notebooks/train_classifier_dl_onnx.ipynb`
- [ ] C-012 [P] Measure LLM zero-shot baseline (Claude API call, 5-class classification) on same test set; record macro-F1 + per-class F1 + cost — `modelserver/notebooks/`
- [x] C-013 [P] ~~Export BGE-small-en-v1.5 to ONNX~~ — superseded by OpenAI hosted embedder decision; no local artifact needed (see docs/DECISIONS.md)

---

## Phase 2 — Real modelserver (Day 2, after Phase 1)

- [ ] C-014 Update `modelserver/pyproject.toml` — add onnxruntime, scikit-learn, numpy — `modelserver/pyproject.toml`
- [x] C-015 Update `modelserver/app.py` — startup sequence: fetch Vault token → load model_card.yaml → load + verify SHA-256 of classifier artifact → read OpenAI API key from Vault (`secret/embed/api_key`) → start server; exit(1) on classifier hash mismatch; warn (not exit) if embed key is empty — `modelserver/app.py`
- [ ] C-016 Implement real `POST /classify` — joblib or onnxruntime inference; log tenant_id, intent, confidence, latency (never message text) — `modelserver/app.py`
- [x] C-017 Implement real `POST /embed` — OpenAI `text-embedding-3-small` with `dimensions=768`; support single text + batch (`texts: list`); return 768-dim vector; 503 if key not configured — `modelserver/app.py`
- [ ] C-018 Fill `modelserver/model_card.yaml` with real training results — macro-F1, per-class F1, latencies for all three approaches; deployed_model, artifact_path, artifact_sha256 — `modelserver/model_card.yaml`
- [ ] C-019 Build modelserver Docker image; verify size < 500MB — `modelserver/Dockerfile`

---

## Phase 3 — Real Guardrails (Day 2-3)

- [ ] C-020 [P] Write platform rails Colang — injection, jailbreak, cross-tenant probe patterns — `guardrails/config/platform/rails.co`
- [ ] C-021 [P] Write platform rails config — `guardrails/config/platform/config.yml`, `prompts.yml`
- [ ] C-022 [P] Write tenant rails Colang template — topic enforcement, persona enforcement — `guardrails/config/tenant_template/rails.co`, `config.yml`
- [ ] C-023 Implement real `guardrails/server.py` — startup: fetch Vault token → load platform rails; per-request: fetch tenant config from backend (60s cache) → PII redaction → platform rails → tenant rails; apply in order, tenant rails cannot weaken platform rails — `guardrails/server.py`
- [ ] C-024 Update `guardrails/Dockerfile` — add nemoguardrails, presidio-analyzer, presidio-anonymizer — `guardrails/Dockerfile`
- [ ] C-025 Build guardrails Docker image; verify size < 600MB — `guardrails/Dockerfile`

---

## Phase 4 — Tracing & Red-Team (Day 3)

- [ ] C-026 [P] Fill real OpenTelemetry spans into `backend/app/tracing.py` — spans: `api.request`, `classifier.call`, `guardrails.input`, `guardrails.output`, `llm.call`, `rag.retrieve`; all include `tenant_id`; none include message content — `backend/app/tracing.py`
- [ ] C-027 [P] Write at least 10 prompt injection probes — `backend/evals/redteam/injection.jsonl`
- [ ] C-028 [P] Write API-level cross-tenant probes — `backend/evals/redteam/cross_tenant.jsonl`
- [ ] C-029 [P] Write redaction test cases — messages containing fake API keys and PII — `backend/evals/redaction/cases.jsonl`

---

## Phase 5 — Documentation (Day 3 / Demo Prep)

- [ ] C-030 Write `docs/SECURITY.md` — threat model, attack surface (injection, jailbreak, cross-tenant, PII), red-team methodology, false-positive policy — `docs/SECURITY.md`
- [ ] C-031 Write `docs/EVALS.md` sections for: classifier eval (what macro-F1 and per-class F1 mean, how to read the model card), redteam gate, redaction gate — `docs/EVALS.md`
- [ ] C-032 Contribute classifier model choice section to `docs/DECISIONS.md` — why deployed_model was chosen over alternatives (latency + cost + F1 tradeoff) — `docs/DECISIONS.md`

---

## Day 1 Completion Checklist (Gate — Owner B is blocked until all pass)

- [ ] `GET http://modelserver:8001/health` → 200
- [ ] `POST http://modelserver:8001/classify` → `{"intent": "ambiguous", "confidence": 0.5}`
- [ ] `POST http://modelserver:8001/embed` → `{"embedding": [0.0, ..., 0.0]}` (768 zeros)
- [ ] Requests without Bearer token → 401 on both services
- [ ] `GET http://guardrails:8002/health` → 200
- [ ] `POST http://guardrails:8002/check/input` → `{"allowed": true, "flagged_categories": [], "redacted_message": "<input>"}`
- [ ] Service tokens read from Vault (not hardcoded)
- [ ] `backend/app/services/redaction.py` committed
