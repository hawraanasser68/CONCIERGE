# Owner D — Implementation Plan
## Widget Auth, Admin UX & CI/CD

---

## Summary

Owner D owns the two surfaces that humans actually touch — the embeddable widget and the Streamlit admin UI — plus the CI pipeline that enforces quality for the whole team. The Day-1 priority is a green CI skeleton and a working widget.js endpoint, so the team has a quality gate from the first commit.

---

## Tech Stack

### Widget
| Layer | Choice | Reason |
|---|---|---|
| Build tool | Vite | Fast HMR, optimised production bundles, code-splitting |
| Framework | React + TypeScript | Component model, type safety, small runtime |
| HTTP | native `fetch` | No library dep needed for simple POST/GET; keeps bundle tiny |
| Package manager | pnpm | Lockfile-based, fast, monorepo-friendly |
| Serving | nginx (multi-stage Docker build) | Serves static files; sets Cache-Control headers correctly |
| **Bundle target** | **< 100KB gzipped** | Hard constraint from brief |

### Admin UI
| Layer | Choice | Reason |
|---|---|---|
| Framework | Streamlit | Rapid internal tool, Python-native, no frontend build step |
| HTTP client | httpx | Async calls to backend API |
| Dependency management | uv | Per-service pyproject.toml |

### CI/CD
| Layer | Choice |
|---|---|
| Platform | GitHub Actions |
| Container orchestration | docker compose (with COMPOSE_PROJECT_NAME isolation) |
| Eval runner | Python scripts (backend/evals/*/run.py) |
| Threshold enforcement | eval_thresholds.yaml at project root |

---

## Architecture Decisions

### Loader as IIFE
The loader script (`loader.js`) runs as an immediately-invoked function expression. It never exports anything to `window`, never pollutes the host page's global namespace. Host pages include it with a single `<script>` tag and forget it exists.

### Token in URL Hash (not query string)
The JWT is passed to the iframe via `window.location.hash` (e.g. `iframe.html#token=...`). Hash fragments are not sent to the server in HTTP requests — the token stays client-side. A query string would appear in server logs.

### Token in Closure (not localStorage)
Storing the JWT in localStorage would persist it across sessions and expose it to any JS on the host page with `localStorage` access. Closure storage means the token lives only in the loader's function scope for the duration of the page session.

### Silent Fail on 403
If the host page origin is not in the widget's `allowed_origins`, the token exchange returns 403. The loader does nothing — no console error, no visible indicator. From the host page's perspective, the widget simply does not appear. This prevents leaking information about which widget IDs exist.

### COMPOSE_PROJECT_NAME Isolation
Every `docker compose` call in CI uses `COMPOSE_PROJECT_NAME=ci-${{ github.run_id }}`. This gives each CI run its own network namespace and container names, preventing port conflicts between concurrent runs on the same runner.

### Threshold Ratchet
`eval_thresholds.yaml` can only go up. Any PR that lowers a threshold is blocked in code review. Owner D enforces this policy — no threshold decrease without written justification and all-owner approval. `redteam.block_rate: 1.0` is permanently locked.

---

## Key Constraints

- Widget bundle < 100KB gzipped — enforced in widget.yml CI job
- JWT stored in closure only — never localStorage or sessionStorage
- Loader fails silently on 403 — no console errors
- CI must use `COMPOSE_PROJECT_NAME: ci-${{ github.run_id }}` on every docker compose call
- LLM API keys in CI come from GitHub Actions secrets — never committed

---

## Dependencies on Other Owners

| Needs | From | When |
|---|---|---|
| `sign_widget_jwt()` in `auth/widget_token.py` | Owner A | Day 1 — token exchange calls this |
| `POST /api/v1/auth/login` | Owner A | Day 1 — Streamlit login requires it |
| Seeded tenants | Owner A | Day 1 — CI smoke test verifies 2 tenants |
| `POST /api/v1/chat/message` | Owner B | Day 2 — widget and agent eval require it |
| CMS endpoints | Owner B | Day 2 — Streamlit content page requires them |
| Red-team probe jsonl files | Owner C | Day 3 — red-team CI gate requires them |
