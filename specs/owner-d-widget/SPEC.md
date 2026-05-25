# Owner D — Widget Auth, Admin UX & CI/CD

**Owner:** Owner D
**Day-1 deliverable:** CI pipeline skeleton green (placeholder thresholds) + hello-world widget served at `GET /widget.js`

---

## Scope

Owner D owns the two surfaces people touch — the widget and the admin UI — plus the CI gates that enforce quality for everyone:

- `widget/` — standalone React widget (Vite + TypeScript)
- `/widget.js` loader script
- `backend/app/routes/widget.py` — token exchange endpoint + widget config endpoint
- Per-tenant `allowed_origins` enforcement (CORS + CSP frame-ancestors + server-side check)
- `admin/` — Streamlit tenant admin UI
- GitHub Actions CI pipeline (`.github/workflows/ci.yml` and `widget.yml`)
- `eval_thresholds.yaml` at project root — committed Day 1 with placeholder values

Owner D does NOT own:
- Database schema or RLS (Owner A)
- Agent, RAG, or memory logic (Owner B)
- Classifier training or guardrails implementation (Owner C)

Owner D's graded deliverables beyond code:
- `eval_thresholds.yaml` — committed Day 1 with placeholder values; tightened as real numbers land
- CI pipeline documentation: the job DAG and threshold-enforcement policy are explained in `docs/EVALS.md` (Owner B/C write the eval methodology; Owner D writes the CI wiring section)

---

## Files and Directories — What Owner D Writes

```
widget/
  package.json                   ← Vite + React + TypeScript + pnpm
  pnpm-lock.yaml
  Dockerfile                     ← multi-stage: build → nginx static
  vite.config.ts                 ← outputs widget.js + widget.css + iframe.html
  index.html                     ← iframe shell (loaded inside the injected iframe)
  public/
    loader.js                    ← /widget.js served to host pages (the <script> tag source)
  src/
    main.tsx                     ← iframe app entry point
    Widget.tsx                   ← chat UI component
    api.ts                       ← token exchange + chat POST + session management
    theme.ts                     ← per-tenant theme from widget config endpoint

admin/
  pyproject.toml                 ← streamlit, httpx, pydantic
  uv.lock
  Dockerfile
  app.py                         ← Streamlit entry, login page
  pages/
    1_widgets.py                 ← widget management + embed snippet
    2_cms.py                     ← CMS page management
    3_guardrails.py              ← agent config: persona, tools, topic rails
    4_leads.py                   ← lead inbox
  lib/
    api_client.py                ← httpx wrapper; all calls go through this

backend/
  app/
    routes/
      widget.py                  ← POST /api/v1/widget/token
                                    GET  /api/v1/widget/{widget_id}/config
                                    (replaces Owner A's Day-1 stub)

.github/
  workflows/
    ci.yml                       ← main pipeline: lint + build + 5 eval gates + smoke test
    widget.yml                   ← widget-specific: tsc check + bundle size gate

eval_thresholds.yaml             ← project root; committed Day 1 with placeholder values
```

Owner D does NOT write anything under:
- `backend/app/main.py`
- `backend/app/auth/`
- `backend/app/tenancy/`
- `backend/app/routes/auth.py`
- `backend/app/routes/manager.py`
- `backend/app/routes/chat.py`
- `backend/app/routes/cms.py`
- `backend/app/services/`
- `backend/app/tools/`
- `backend/migrations/`
- `modelserver/`
- `guardrails/`
- `docker-compose.yml`

---

## React Widget

### What it is

A standalone Vite + React + TypeScript app. The build output is served via nginx from the `widget/` Docker container. It renders inside an `<iframe>` that the loader script injects into the host page. The host page never shares its DOM or JS scope with the widget.

### Bundle target

Under 100KB gzipped. No heavy dependencies beyond React and a small HTTP client.

### Loader script — `widget/public/loader.js`

This is the file that embedding sites include with a `<script>` tag:

```html
<script
  src="https://concierge.example.com/widget.js"
  data-widget-id="your-widget-uuid"
></script>
```

The loader is an IIFE (immediately invoked function expression) so it never pollutes the host page's global namespace.

What the loader does:
1. Read `data-widget-id` from the current `<script>` element
2. Detect `window.location.origin`
3. `POST /api/v1/widget/token` with `{ widget_id, origin }`
4. On success: receive `{ token, session_id }` — store in a closure (not localStorage, not sessionStorage — session-only memory)
5. Create an `<iframe>` pointing to `iframe.html?token=...&session_id=...` (token in URL hash — not query string, so it stays client-side)
6. Inject the iframe into the host page
7. On HTTP 403 (ORIGIN_BLOCKED): silently do nothing — no console errors, no visible indicator. From the host page's perspective, the widget simply does not appear.

### Widget component — `widget/src/Widget.tsx`

On iframe load:
1. Extract `token` and `session_id` from `window.location.hash`
2. `GET /api/v1/widget/{widget_id}/config` — receives `{ greeting, persona_name, theme }`
3. Display the greeting message

On each user message sent:
1. Append to message list optimistically
2. `POST /api/v1/chat/message` with:
   - `Authorization: Bearer <token>`
   - `X-Session-Id: <session_id>`
   - Body: `{ "message": "user text" }`
3. Append assistant response when it arrives
4. Handle HTTP 401 (expired token): "Session expired — please refresh the page" — do NOT silently re-request a token
5. Handle HTTP 429 (rate limit): "Too many messages — please wait a moment"
6. Handle HTTP 503: "I'm having trouble right now — please try again"

---

## Widget Token Exchange Endpoint

`backend/app/routes/widget.py`

**`POST /api/v1/widget/token`** — public endpoint, no user auth required

```python
@router.post("/token")
async def exchange_widget_token(
    body: WidgetTokenRequest,       # { widget_id: UUID, origin: str }
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> WidgetTokenResponse:

    # 1. Look up widget by widget_id — 404 if not found or inactive
    widget = await session.get(Widget, body.widget_id)
    if not widget or not widget.is_active:
        raise HTTPException(404)

    # 2. Validate origin — 403 if not in widget.allowed_origins
    if body.origin not in widget.allowed_origins:
        raise HTTPException(403, detail="Origin not allowed", headers={"X-Error-Code": "ORIGIN_BLOCKED"})

    # 3. Generate session_id
    session_id = str(uuid.uuid4())

    # 4. Sign JWT using Owner A's widget_token.py helper
    from app.auth.widget_token import sign_widget_jwt
    token = sign_widget_jwt(
        tenant_id=str(widget.tenant_id),
        widget_id=str(widget.id),
        origin=body.origin,
        session_id=session_id,
    )

    return WidgetTokenResponse(token=token, session_id=session_id, expires_at=...)
```

**`GET /api/v1/widget/{widget_id}/config`** — public endpoint

```python
@router.get("/{widget_id}/config")
async def get_widget_config(widget_id: UUID, session: AsyncSession = Depends(get_session)):
    widget = await session.get(Widget, widget_id)
    if not widget or not widget.is_active:
        raise HTTPException(404)
    return {
        "greeting": widget.greeting,
        "persona_name": widget.persona_name,
        "theme": {"primary_color": "#0066cc"}   # future: from widget config
    }
```

---

## Per-Tenant Origin Allowlist

### CORS

`CORSMiddleware` configured with per-request origin validation. Allowed origins come from `widget.allowed_origins` in the database — not from a global env var. The middleware looks up the widget's allowed origins for the incoming `Origin` header.

### CSP frame-ancestors

The widget iframe endpoint responds with:
```
Content-Security-Policy: frame-ancestors 'self' https://example.com
```

The `frame-ancestors` value is populated from `widget.allowed_origins` at request time — not a static nginx config.

### Server-side origin check (the real guard)

CORS and CSP are browser-enforced. A `curl` with a copied `widget_id` ignores CORS entirely.

The server-side check in the token exchange endpoint (`body.origin not in widget.allowed_origins`) is what stops non-browser callers. This is enforced regardless of whether the request came from a browser.

Owner A's auth middleware additionally validates on every chat request that the `origin` claim in the JWT matches the incoming `Origin` header. Mismatch → HTTP 403.

Owner D writes a CI test: use `httpx` (no CORS) to call the token exchange with an origin not in the allowlist — assert HTTP 403.

---

## Admin Streamlit UI

`admin/` — calls the backend API via `lib/api_client.py`. Never touches the database directly.

### Login (`admin/app.py`)

- Email + password → `POST /api/v1/auth/login` → JWT stored in `st.session_state["token"]`
- Role check: if `role != "tenant_admin"` → "Access denied"
- All subsequent API calls include `Authorization: Bearer <token>`

### Page: Widgets (`admin/pages/1_widgets.py`)

- List widgets: `GET /api/v1/admin/widgets`
- Create widget form: name, allowed_origins (comma-separated), greeting, persona_name → `POST /api/v1/admin/widgets`
- Edit: `PUT /api/v1/admin/widgets/{id}`
- Toggle active: `PATCH /api/v1/admin/widgets/{id}/status`
- Embed snippet display:

```html
<script
  src="https://concierge.example.com/widget.js"
  data-widget-id="{widget_id}"
></script>
```

### Page: CMS Content (`admin/pages/2_cms.py`)

- List pages: `GET /api/v1/cms/pages`
- Create page form: title, slug, content (textarea), publish toggle → `POST /api/v1/cms/pages`
- Edit: `PUT /api/v1/cms/pages/{id}`
- Delete (with confirmation): `DELETE /api/v1/cms/pages/{id}`
- "Indexing in progress..." badge for recently updated pages (embedding pipeline is async)

### Page: Agent & Guardrail Config (`admin/pages/3_guardrails.py`)

- Current config: `GET /api/v1/cms/agent-config`
- Editable fields:
  - `persona_name` (text input)
  - `persona_description` (textarea)
  - `enabled_tools` (multiselect: rag_search, capture_lead, escalate)
  - `blocked_topics` (text area, comma-separated)
  - `allowed_topics` (text area)
  - `max_tool_iterations` (number input, 1–10)
- Save: `PUT /api/v1/cms/agent-config`
- Note visible to user: "Platform security rails (injection, jailbreak detection, PII protection) are always active and cannot be modified here."

### Page: Leads (`admin/pages/4_leads.py`)

- Paginated list: `GET /api/v1/admin/leads?page=1&page_size=20`
- Columns: name, contact, intent, created_at, classifier_score

---

## CI/CD Pipeline

### `.github/workflows/ci.yml`

Triggered on every push to every branch.

**Job DAG:**
```
lint-and-typecheck
        └── build-images
                ├── smoke-test
                │       ├── eval-classifier
                │       ├── eval-agent
                │       ├── eval-rag
                │       ├── eval-redteam
                │       └── eval-redaction
                └── (widget.yml runs in parallel — see below)
```

**Job: lint-and-typecheck**
```yaml
steps:
  - name: Python lint + type check
    run: |
      pip install ruff mypy
      ruff check backend/ admin/ modelserver/ guardrails/
      mypy backend/app/

  - name: TypeScript check (fast path — full check is in widget.yml)
    run: |
      cd widget && pnpm install --frozen-lockfile && pnpm tsc --noEmit
```

**Job: build-images**
```yaml
steps:
  - name: Build all images
    run: docker compose build --parallel

  - name: Check image sizes
    run: |
      docker image inspect concierge-modelserver --format='{{.Size}}' | \
        awk '{if ($1 > 500000000) {print "ERROR: modelserver image exceeds 500MB"; exit 1}}'
```

**Job: smoke-test**
```yaml
steps:
  - name: Start stack
    run: |
      cp .env.example .env
      COMPOSE_PROJECT_NAME=ci-${{ github.run_id }} docker compose up -d --wait --timeout 120

  - name: Health checks
    run: |
      curl -f http://localhost:8000/health
      curl -f http://localhost:8001/health
      curl -f http://localhost:8002/health
      curl -f http://localhost:3000/widget.js

  - name: Migration applied
    run: docker compose exec backend alembic current | grep "(head)"

  - name: Two seeded tenants exist
    run: |
      docker compose exec db psql -U postgres -c "SELECT count(*) FROM tenants;" | grep -E "^\s+2"

  - name: Teardown
    if: always()
    run: COMPOSE_PROJECT_NAME=ci-${{ github.run_id }} docker compose down -v
```

**Job: eval-classifier**
```yaml
steps:
  - name: Run classifier eval
    run: |
      COMPOSE_PROJECT_NAME=ci-${{ github.run_id }} docker compose up -d --wait
      python backend/evals/classifier/run.py \
        --endpoint http://localhost:8001/classify \
        --golden backend/evals/classifier/golden.jsonl \
        --thresholds eval_thresholds.yaml
      # run.py exits 1 if macro_f1 < eval_thresholds.yaml::classifier.macro_f1
```

**Job: eval-agent**
```yaml
steps:
  - name: Run agent tool-selection eval
    run: |
      python backend/evals/agent_tool_selection/run.py \
        --endpoint http://localhost:8000/api/v1/chat/message \
        --golden backend/evals/agent_tool_selection/golden.jsonl \
        --tenant-token $TENANT_A_TOKEN \
        --thresholds eval_thresholds.yaml
```

**Job: eval-rag**
```yaml
steps:
  - name: Seed CMS content for Tenant A
    run: python backend/evals/rag/seed.py --endpoint http://localhost:8000

  - name: Run RAG eval
    run: |
      python backend/evals/rag/run.py \
        --endpoint http://localhost:8000/api/v1/chat/message \
        --golden backend/evals/rag/golden.jsonl \
        --thresholds eval_thresholds.yaml
```

**Job: eval-redteam**
```yaml
steps:
  - name: Run red-team eval
    run: |
      python backend/evals/redteam/run.py \
        --endpoint http://localhost:8000/api/v1/chat/message \
        --injection-probes backend/evals/redteam/injection.jsonl \
        --cross-tenant-probes backend/evals/redteam/cross_tenant.jsonl \
        --tenant-a-token $TENANT_A_TOKEN \
        --thresholds eval_thresholds.yaml
      # EVERY probe must be blocked — exit 1 if any passes
```

**Job: eval-redaction**
```yaml
steps:
  - name: Run redaction eval
    run: |
      python backend/evals/redaction/run.py \
        --endpoint http://localhost:8000/api/v1/chat/message \
        --cases backend/evals/redaction/cases.jsonl \
        --thresholds eval_thresholds.yaml
      # Checks API response AND stdout logs — any raw PII/key → exit 1
```

### `.github/workflows/widget.yml`

Triggered on every push.

```yaml
steps:
  - name: TypeScript strict check
    run: cd widget && pnpm install --frozen-lockfile && pnpm tsc --noEmit --strict

  - name: Build bundle
    run: cd widget && pnpm build

  - name: Check bundle size
    run: |
      BUNDLE_SIZE=$(gzip -c widget/dist/assets/*.js | wc -c)
      echo "Bundle size: ${BUNDLE_SIZE} bytes gzipped"
      if [ $BUNDLE_SIZE -gt 102400 ]; then
        echo "ERROR: widget bundle exceeds 100KB gzipped"
        exit 1
      fi
```

---

## eval_thresholds.yaml

`eval_thresholds.yaml` at project root. Committed Day 1 with placeholder values. Never lower a threshold to make CI pass.

```yaml
# Committed Day 1 — tighten as real numbers land during the week

classifier:
  macro_f1: 0.0             # placeholder — raise to real value after Day 2 training

agent:
  tool_accuracy: 0.0        # placeholder — raise after agent wired (Day 3)

rag:
  hit_at_5: 0.0             # placeholder — raise after RAG functional (Day 2-3)
  faithfulness: 0.0
  answer_relevancy: 0.0

redteam:
  block_rate: 1.0           # 100% from Day 1 — never lower this

redaction:
  leak_rate: 0.0            # 0% leak rate — any raw PII/secret fails CI

widget:
  bundle_size_kb_gzipped: 100   # never increase this
```

---

## What Owner D Depends On

| Dependency | From | When |
|---|---|---|
| `POST /api/v1/auth/login` | Owner A | Day 1 — Streamlit login requires it |
| `sign_widget_jwt` in `auth/widget_token.py` | Owner A | Day 1 — token exchange endpoint calls this |
| Seeded tenants | Owner A | Day 1 — CI smoke test verifies 2 tenants |
| `POST /api/v1/chat/message` | Owner B | Day 2 — widget and agent eval require it |
| CMS endpoints | Owner B | Day 2 — Streamlit content page requires them |
| Red-team probe jsonl files | Owner C | Day 3 — red-team CI gate requires them |

---

## What Owner D Delivers That Others Depend On

| Deliverable | Used by | When |
|---|---|---|
| CI pipeline (green even with 0.0 placeholder thresholds) | Everyone — no merge without CI | Day 1 |
| `eval_thresholds.yaml` | All eval jobs | Day 1 |
| `GET /widget.js` → 200 | Demo | Day 1 (hello-world) |
| `POST /api/v1/widget/token` endpoint | Widget, auth middleware | Day 1 |

---

## Day 1 Checklist

- [ ] `.github/workflows/ci.yml` exists and is green (all gates pass with placeholder thresholds)
- [ ] `.github/workflows/widget.yml` exists and is green
- [ ] `eval_thresholds.yaml` committed at project root
- [ ] `widget/` Docker image builds — serves hello-world at `GET /widget.js`
- [ ] `POST /api/v1/widget/token` returns signed JWT for a valid widget_id + allowed origin
- [ ] `POST /api/v1/widget/token` returns HTTP 403 for a blocked origin
- [ ] Smoke test job green: 4 health checks pass, migration applied, 2 tenants seeded

---

## Friday Demo Requirements

The brief specifies three things that must be live and demonstrable at the Friday presentation. Owner D is responsible for all three:

### 1. Widget loads on an allowed host

A live browser tab at an allowed origin (e.g. `http://localhost:5500` or `https://demo.example.com`) loads the widget, shows the greeting, and exchanges a message. The `allowed_origins` for the demo widget must be pre-configured in the database before the demo.

### 2. Widget is blocked on a disallowed host (real browser console)

Open a second tab on a different origin (e.g. `http://evil.example.com` or simply a different localhost port not in the allowlist). Include the `<script>` tag with the same `data-widget-id`. The widget must silently not appear. Open the browser's developer console on-screen during the demo — no errors, no widget, no token.

This demonstrates the server-side origin check (`403 ORIGIN_BLOCKED`) and the loader's silent-fail behavior.

### 3. Stale token rejected by the API (raw curl)

Run a live `curl` in the terminal during the demo with an expired or modified JWT:

```bash
curl -X POST http://localhost:8000/api/v1/chat/message \
  -H "Authorization: Bearer <stale_or_tampered_token>" \
  -H "X-Session-Id: fake-session-id" \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'
# Expected: HTTP 401
```

The response must be 401. This demonstrates that auth middleware is enforced at the API level, not just in the browser.

Owner D must rehearse all three steps before the demo. Populate `demo/README.md` (the directory exists at the project root) with the exact commands and setup steps so any team member can run the demo if needed.

---

## Edge Cases

**Stale widget token:**
Token expires after 1 hour. The widget catches HTTP 401 and shows: "Session expired — please refresh the page." It does NOT silently re-fetch a token — that requires the loader flow which lives in the parent page, not the iframe.

**Origin configured as `http://` vs `https://`:**
An admin who types `http://example.com` when their site is `https://example.com` will get ORIGIN_BLOCKED silently. The Streamlit widget management page shows the current `allowed_origins` list clearly so they can debug without contacting support.

**Multiple concurrent CI runs:**
Use `COMPOSE_PROJECT_NAME: ci-${{ github.run_id }}` on every `docker compose` call to avoid port conflicts between concurrent CI runs.

**LLM API key absent in CI for eval jobs:**
Eval jobs that call the agent (and thus the LLM) must use real API keys. Set them as GitHub Actions secrets. The CI job reads `LLM_API_KEY` from the Actions secret store — never committed to the repo. The smoke test and classifier eval do not require LLM keys.

**Threshold regression:**
Any PR that lowers a threshold in `eval_thresholds.yaml` is blocked in code review. Owner D enforces: no threshold decrease without written justification in the PR description and approval from all owners.

**Widget.js cached at wrong version:**
The nginx container serving `widget.js` must set `Cache-Control: no-cache` for `widget.js` (the loader) but may set long-cache for the widget bundle files (which are content-hashed by Vite). This ensures the loader always reflects the latest embed instructions.
