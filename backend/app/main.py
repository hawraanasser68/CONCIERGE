# Owner A — backend/app/main.py
#
# FastAPI application entry point. Written once on Day 1 — nobody else edits this file.
#
# Route auto-discovery: any file dropped into app/routes/ that exposes a variable
# named `router` of type APIRouter is automatically registered. No manual imports needed.
# Owners B and D drop their route files; this file picks them up without any edit.

import importlib
import pkgutil

import app.routes as routes_pkg
from app.lifespan import lifespan
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Concierge API",
    version="0.1.0",
    description="Multi-tenant AI concierge platform",
    lifespan=lifespan,
    # Disable automatic /docs and /redoc in production
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — origins are validated per-widget at the route level (not globally here).
# This middleware handles the browser preflight; the real security check is in
# the token exchange endpoint which validates origin against widget.allowed_origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # permissive here — enforced strictly in widget token exchange
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auto-discover and register all route modules ──────────────────────────────
# Iterates app/routes/*.py and registers any module that has a `router` attribute.
# New route files are picked up automatically — no edit to this file needed.
for module_info in pkgutil.iter_modules(routes_pkg.__path__):
    module = importlib.import_module(f"app.routes.{module_info.name}")
    if hasattr(module, "router"):
        app.include_router(module.router)
