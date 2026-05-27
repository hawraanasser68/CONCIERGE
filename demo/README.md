# Concierge — Friday Demo Runbook (Owner D — D-030)

Three live checks that prove the security wall. Rehearse in order; each takes ~30s.

---

## Prereqs

```bash
cp .env.example .env
# Fill ANTHROPIC_API_KEY (or whatever LLM_API_KEY) in Vault before running.
docker compose up -d --wait --timeout 180
docker compose exec -T -w /app backend python -m scripts.seed_dev_data
```

After the seed step, `psql` to grab the demo widget id once:

```bash
docker compose exec -T db psql -U concierge -d concierge -tAc \
  "SELECT id FROM widgets WHERE tenant_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' LIMIT 1;"
```

Export it for the rest of the demo:

```bash
export WIDGET_ID=<paste-uuid-here>
```

Also start a tiny host-page server on a port the widget's `allowed_origins` permits (seed sets `http://localhost:3000`). Easiest:

```bash
cd demo
python -m http.server 3000
```

(That serves `demo/allowed.html` and `demo/blocked.html` — see below for the two-file snippet.)

---

## Demo 1 — Widget loads on an **allowed** host

**Setup:** `demo/allowed.html` (served on `http://localhost:3000`):

```html
<!doctype html>
<html><head><title>Allowed Host Demo</title></head>
<body>
  <h1>Bloom Florista</h1>
  <p>This page's origin is in the widget's allowed_origins.</p>
  <script
    src="http://localhost:3000/widget.js"
    data-widget-id="<WIDGET_ID>"
  ></script>
</body></html>
```

**Run:** open `http://localhost:3000/allowed.html` in a browser with DevTools open.

**Expected:** chat widget appears in the bottom-right corner, shows the configured greeting ("Hi! Welcome to Bloom Florista..."), and a user message round-trips through the chat endpoint. DevTools Network tab shows a `200` on `POST /api/v1/widget/token` and `200` on `POST /api/v1/chat/message`.

---

## Demo 2 — Widget is **silently blocked** on a disallowed host

**Setup:** start a second static server on a port NOT in `allowed_origins`:

```bash
cd demo
python -m http.server 5500
```

`demo/blocked.html` (served on `http://localhost:5500`):

```html
<!doctype html>
<html><head><title>Blocked Host Demo</title></head>
<body>
  <h1>evil.example.com</h1>
  <p>This origin is NOT in allowed_origins. The widget must not appear.</p>
  <script
    src="http://localhost:3000/widget.js"
    data-widget-id="<WIDGET_ID>"
  ></script>
</body></html>
```

**Run:** open `http://localhost:5500/blocked.html` with DevTools open.

**Expected:**
- No widget visible in the corner.
- DevTools Console: **no errors**, **no logs** from the loader (it silently no-ops on 403).
- DevTools Network: `POST /api/v1/widget/token` returns `403` with header `X-Error-Code: ORIGIN_BLOCKED`. That is the only visible signal.

**Why this matters:** proves CORS alone isn't the boundary — the server-side allowlist check is doing the work, and the loader leaks no information to the host page.

---

## Demo 3 — Stale token rejected by the API (raw `curl`)

This bypasses the browser entirely to prove the API enforces JWT validation regardless of CORS.

**Run a tampered or expired token:**

```bash
curl -i -X POST http://localhost:8000/api/v1/chat/message \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.tampered.payload" \
  -H "X-Session-Id: 00000000-0000-0000-0000-000000000000" \
  -H "Origin: http://localhost:3000" \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'
```

**Expected:** `HTTP/1.1 401 Unauthorized` with `{"detail":"Invalid token"}`.

For an **expired** (rather than tampered) token, mint a token now and wait >1 hour (TTL is 3600s), then replay — same 401.

**Why this matters:** the auth middleware enforces signature + expiry + tenant-active checks server-side; a bad token is rejected at the API edge regardless of where the request originated.

---

## Cleanup

```bash
docker compose down -v
```

Drops all containers, volumes (Postgres data, MinIO blobs, Redis sessions). Re-running the prereq block from scratch reproduces a clean demo state in ~60s.

---

## Demo prep checklist (D-031, D-032)

Before Friday:

- [ ] Confirm seed widget exists and `allowed_origins=["http://localhost:3000"]`
- [ ] Confirm `docker compose up -d --wait` brings all 6 services healthy in <3 min
- [ ] Confirm widget bundle is under 100KB gzipped on latest `widget.yml` CI run
- [ ] Confirm CI is fully green on `main` (especially `eval-redteam` and `eval-redaction`)
- [ ] Rehearse all three demos end-to-end, in order, with screen recording on
- [ ] Test on a clean browser profile (no extensions interfering with iframe / Console output)
