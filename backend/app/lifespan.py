# Owner A — backend/app/lifespan.py
#
# FastAPI lifespan: runs startup logic before the first request,
# shutdown logic after the last. Stores shared resources in app.state
# so every request handler can access them via request.app.state.
#
# Startup order matters:
#   1. Logging (needed for all subsequent log lines)
#   2. Vault (secrets needed before DB/Redis connect)
#   3. DB engine + run migrations
#   4. Redis pool
#   5. MinIO client (for tenant blob erasure)
#   6. httpx session (for calling modelserver + guardrails)
#   7. Tracing (needs the app + engine)

from contextlib import asynccontextmanager

import hvac
import redis.asyncio as aioredis
import structlog
from httpx import AsyncClient
from minio import Minio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.logging_setup import setup_logging

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()

    # ── 1. Logging ────────────────────────────────────────────────────────────
    setup_logging(is_production=settings.is_production)
    log.info("startup_begin", environment=settings.environment)

    # ── 2. Vault — fetch all secrets ─────────────────────────────────────────
    vault = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
    if not vault.is_authenticated():
        raise RuntimeError("Vault authentication failed — check VAULT_ADDR and VAULT_TOKEN")

    def _secret(path: str, key: str) -> str:
        """Read a single key from a KV v2 secret path."""
        data = vault.secrets.kv.v2.read_secret_version(path=path)
        return data["data"]["data"][key]

    app.state.widget_signing_key = _secret("widget/signing_key", "key")
    app.state.modelserver_token = _secret("svc/modelserver", "token")
    app.state.guardrails_token = _secret("svc/guardrails", "token")

    llm_api_key = _secret("llm/api_key", "key")
    if not llm_api_key:
        log.warning("llm_api_key_empty", msg="LLM calls will fail until this is set in Vault")
    app.state.llm_api_key = llm_api_key

    log.info("vault_secrets_loaded")

    # ── 3. Database engine ────────────────────────────────────────────────────
    engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,   # validates connections before use — handles DB restarts
        echo=False,
    )
    app.state.engine = engine
    app.state.session_factory = async_sessionmaker(
        engine, expire_on_commit=False
    )
    log.info("db_engine_created")

    # ── 4. Redis pool ─────────────────────────────────────────────────────────
    redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    await redis.ping()   # fail fast if Redis is unreachable
    app.state.redis = redis
    log.info("redis_connected")

    # ── 5. MinIO client ───────────────────────────────────────────────────────
    minio_access_key = _secret("minio/access_key", "key")
    minio_secret_key = _secret("minio/secret_key", "key")
    app.state.minio = Minio(
        settings.minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=False,
    )
    log.info("minio_client_created")

    # ── 6. Shared httpx session ───────────────────────────────────────────────
    # Reused for all calls to modelserver and guardrails.
    # Timeout: 10s total — guardrails must respond fast enough for real-time chat.
    app.state.http_client = AsyncClient(timeout=10.0)
    log.info("http_client_created")

    # ── 6. Tracing ────────────────────────────────────────────────────────────
    from app.tracing import setup_tracing
    setup_tracing(app, engine, settings.otel_exporter_otlp_endpoint)
    log.info("tracing_configured")

    log.info("startup_complete")
    yield   # app is now serving requests

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await app.state.http_client.aclose()
    await redis.aclose()
    await engine.dispose()
    log.info("shutdown_complete")
