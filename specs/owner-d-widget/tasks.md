# Owner D — Task List

Format: `[ID] [P?] Description — file`
`[P]` = can run in parallel with other `[P]` tasks in the same phase.

**Day-1 priority: green CI skeleton + /widget.js endpoint. The team has no quality gate until D-001 is done.**

---

## Phase 0 — CI Skeleton (Day 1, first — everything else can be parallel after this)

- [ ] D-001 Write `.github/workflows/ci.yml` — complete job DAG: lint-and-typecheck → build-images → smoke-test → {eval-classifier, eval-agent, eval-rag, eval-redteam, eval-redaction} in parallel; all eval jobs use `COMPOSE_PROJECT_NAME: ci-${{ github.run_id }}`; eval jobs use placeholder thresholds (all 0.0 except redteam 1.0) so CI is green on Day 1 — `.github/workflows/ci.yml`
- [ ] D-002 Write `.github/workflows/widget.yml` — TypeScript strict check + bundle build + size gate (< 100KB gzipped) — `.github/workflows/widget.yml`
- [ ] D-003 Verify `eval_thresholds.yaml` has correct structure and `redteam.block_rate: 1.0` is set — `eval_thresholds.yaml`

---

## Phase 1 — Widget Hello-World (Day 1, parallel with D-001)

- [ ] D-004 [P] Write `widget/Dockerfile` — multi-stage: node build → nginx static serving; exposes port 3000 — `widget/Dockerfile`
- [ ] D-005 [P] Write `widget/public/loader.js` stub — IIFE that reads `data-widget-id` and serves `GET /widget.js` returning 200 (hello-world content) — `widget/public/loader.js`
- [ ] D-006 [P] Write `widget/package.json` + `widget/vite.config.ts` — minimal Vite + React + TypeScript config — `widget/package.json`, `widget/vite.config.ts`
- [ ] D-007 [P] Write `widget/index.html` — iframe shell (host for the chat UI) — `widget/index.html`
- [ ] D-008 Verify `GET http://localhost:3000/widget.js` → 200 (required by smoke test)

---

## Phase 2 — Token Exchange Endpoint (Day 1, depends on Owner A auth being live)

- [ ] D-009 Write `backend/app/routes/widget.py` — replace A's 501 stub; implement `POST /api/v1/widget/token`: look up widget → validate origin → generate session_id → call `sign_widget_jwt()` → return token; implement `GET /api/v1/widget/{id}/config` → return greeting + persona_name + theme — `backend/app/routes/widget.py`
- [ ] D-010 Write CI test: `httpx` call with origin not in allowlist → assert HTTP 403 — `backend/tests/`

---

## Phase 3 — Full Loader & Widget UI (Day 2)

- [ ] D-011 Write real `widget/public/loader.js` IIFE — reads `data-widget-id`, detects `window.location.origin`, POSTs `/token`, stores token in closure (not localStorage), injects `<iframe src="iframe.html#token=...&session_id=...">`, silently does nothing on 403 — `widget/public/loader.js`
- [ ] D-012 [P] Write `widget/src/api.ts` — `exchangeToken()`, `getConfig()`, `sendMessage()`; token stored in closure; `X-Session-Id` header on every chat call — `widget/src/api.ts`
- [ ] D-013 [P] Write `widget/src/theme.ts` — per-tenant theme (primary_color from widget config) — `widget/src/theme.ts`
- [ ] D-014 [P] Write `widget/src/Widget.tsx` — chat UI: message list, input box, send button; on load: extract token from hash → GET config → show greeting; on send: POST chat → append response; handle 401 ("Session expired"), 429 ("Too many messages"), 503 ("I'm having trouble") — `widget/src/Widget.tsx`
- [ ] D-015 [P] Write `widget/src/main.tsx` — iframe app entry point; renders `<Widget />` — `widget/src/main.tsx`
- [ ] D-016 Build widget bundle; verify < 100KB gzipped

---

## Phase 4 — Admin Streamlit UI (Day 2-3)

- [ ] D-017 Write `admin/app.py` — Streamlit entry: login page → `POST /api/v1/auth/login` → store JWT in `st.session_state`; role check (`tenant_admin` only); navigation — `admin/app.py`
- [ ] D-018 [P] Write `admin/lib/api_client.py` — httpx wrapper; all calls include `Authorization: Bearer <token>`; handles 401 by clearing session — `admin/lib/api_client.py`
- [ ] D-019 [P] Write `admin/pages/1_widgets.py` — list widgets, create form, edit, toggle active, embed snippet display — `admin/pages/1_widgets.py`
- [ ] D-020 [P] Write `admin/pages/2_cms.py` — list pages, create/edit/delete, publish toggle, "indexing in progress" badge — `admin/pages/2_cms.py`
- [ ] D-021 [P] Write `admin/pages/3_guardrails.py` — GET/PUT agent-config: persona, tools multiselect, blocked/allowed topics, max_tool_iterations; note about locked platform rails — `admin/pages/3_guardrails.py`
- [ ] D-022 [P] Write `admin/pages/4_leads.py` — paginated lead list with columns: name, contact, intent, created_at, classifier_score — `admin/pages/4_leads.py`
- [ ] D-023 Write `admin/pyproject.toml` and `admin/Dockerfile` — `admin/pyproject.toml`, `admin/Dockerfile`

---

## Phase 5 — Full CI Pipeline (Day 3)

- [ ] D-024 Complete `eval-classifier` job — calls Owner B's `run.py`, reads thresholds, exits 1 if below — `.github/workflows/ci.yml`
- [ ] D-025 [P] Complete `eval-agent` job — sends golden examples to `/chat/message` with Tenant A JWT — `.github/workflows/ci.yml`
- [ ] D-026 [P] Complete `eval-rag` job — seeds CMS content (calls Owner B's `seed.py`), runs Owner B's RAG eval — `.github/workflows/ci.yml`
- [ ] D-027 [P] Complete `eval-redteam` job — runs all injection + cross-tenant probes; any probe passing CI → exit 1 — `.github/workflows/ci.yml`
- [ ] D-028 [P] Complete `eval-redaction` job — checks API response AND stdout logs for raw PII/secrets — `.github/workflows/ci.yml`
- [ ] D-029 Tighten `eval_thresholds.yaml` with real numbers from Day 2-3 training and eval runs — `eval_thresholds.yaml`

---

## Phase 6 — Demo Prep (Before Friday)

- [ ] D-030 Write `demo/README.md` — exact step-by-step commands for all three demo checks:
  1. Widget loads on allowed host (pre-configure `allowed_origins` for demo widget)
  2. Widget silently blocked on disallowed host (browser console open)
  3. Stale/tampered JWT → `curl` → HTTP 401 — `demo/README.md`
- [ ] D-031 Rehearse all three demo checks end-to-end; confirm no console errors on blocked host
- [ ] D-032 Confirm CI is fully green with real thresholds before Friday presentation

---

## Day 1 Completion Checklist (Gate)

- [ ] `.github/workflows/ci.yml` exists and is green (all gates pass with placeholder thresholds)
- [ ] `.github/workflows/widget.yml` exists and is green
- [ ] `eval_thresholds.yaml` committed with correct structure and `redteam.block_rate: 1.0`
- [ ] `widget/` Docker image builds — `GET /widget.js` → 200
- [ ] `POST /api/v1/widget/token` → signed JWT for valid widget_id + allowed origin
- [ ] `POST /api/v1/widget/token` → HTTP 403 for blocked origin
- [ ] Smoke test job green: 4 health checks pass, migration applied, 2 tenants seeded
