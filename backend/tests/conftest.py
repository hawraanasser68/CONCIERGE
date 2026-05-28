# Owner A — backend/tests/conftest.py
#
# Shared pytest fixtures for unit, integration, and e2e tests.
#
# Key design decisions:
#   1. The real lifespan (Vault → DB → Redis) is replaced with a no-op so tests
#      never need a running Vault or external services.
#   2. app.state is populated manually with test values before each client fixture.
#   3. FastAPI dependency_overrides replace get_session, get_current_user, etc.
#      so individual test functions receive predictable inputs.
#   4. FakeModelserverTransport and FakeLLMTransport intercept all httpx calls —
#      no real network traffic in any test that uses the `client` fixture.

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── Fixed test constants ───────────────────────────────────────────────────────
# These match the seeded rows in 0001_initial_schema.py and all eval fixtures.
# Never change them.

TENANT_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://concierge:concierge@localhost:5432/concierge_test",
)

# ── Database ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
async def test_engine():
    """
    Session-scoped async engine. Creates all tables at session start,
    drops them at session end. Each test gets a rolled-back transaction
    so rows never bleed between tests.
    """
    from app.models.base import Base

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped DB session. Rolls back after each test so the DB
    stays clean without needing a full table truncate between tests.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ── Fake users ────────────────────────────────────────────────────────────────

@pytest.fixture
def tenant_admin():
    """Fake tenant_admin user for Tenant A. Injected via dependency_overrides."""
    from app.models.user import User
    return User(
        id=uuid.uuid4(),
        email="admin@bloom-florista.test",
        hashed_password="",
        role="tenant_admin",
        tenant_id=TENANT_A_ID,
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )


@pytest.fixture
def tenant_manager():
    """Fake tenant_manager user (no tenant_id). Injected via dependency_overrides."""
    from app.models.user import User
    return User(
        id=uuid.uuid4(),
        email="platform@concierge.test",
        hashed_password="",
        role="tenant_manager",
        tenant_id=None,
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )


# ── Redis mock ────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    """
    MagicMock that covers all Redis calls made by rate_limiter.py and
    the conversation memory layer (Owner B). Override individual AsyncMocks
    in a test with monkeypatch when you need specific return values.
    """
    redis = MagicMock()
    redis.get    = AsyncMock(return_value=None)
    redis.set    = AsyncMock(return_value=True)
    redis.incr   = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.keys   = AsyncMock(return_value=[])
    redis.delete = AsyncMock(return_value=0)
    redis.ping   = AsyncMock(return_value=True)
    redis.lrange = AsyncMock(return_value=[])
    redis.lpush  = AsyncMock(return_value=1)
    redis.ltrim  = AsyncMock(return_value=True)
    redis.aclose = AsyncMock(return_value=None)

    pipeline = MagicMock()
    pipeline.incr    = MagicMock(return_value=pipeline)
    pipeline.expire  = MagicMock(return_value=pipeline)
    pipeline.execute = AsyncMock(return_value=[1, True])
    redis.pipeline   = MagicMock(return_value=pipeline)

    return redis


# ── Fake HTTP transports ──────────────────────────────────────────────────────

class FakeModelserverTransport:
    """
    Intercepts all POST /classify calls made by Owner B's classifier_client.
    Default: returns intent=faq, confidence=0.95.
    Override with monkeypatch in tests that need a different intent or confidence.
    """

    def __init__(self, intent: str = "faq", confidence: float = 0.95):
        self.intent = intent
        self.confidence = confidence

    async def handle_async_request(self, request: Request) -> Response:
        return Response(
            200,
            json={"intent": self.intent, "confidence": self.confidence},
        )


class FakeLLMTransport:
    """
    Intercepts all Anthropic messages API calls.
    Returns a fixed one-sentence response so tests don't need a real API key.
    Usage: pass as http_client transport in the client fixture when testing chat paths.
    """

    async def handle_async_request(self, request: Request) -> Response:
        return Response(
            200,
            json={
                "id": "msg_test_00000000",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "I can help you with that!"}],
                "model": "claude-haiku-4-5-20251001",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
        )


# ── FastAPI test client ────────────────────────────────────────────────────────

@pytest.fixture
async def client(test_engine, db_session, fake_redis, tenant_admin):
    """
    Async HTTP client wired against the FastAPI app with all external services mocked.

    What this fixture does:
    - Replaces the real lifespan (Vault → DB → Redis) with a no-op so no
      external services need to be running.
    - Populates app.state with test-safe values (fake signing key, fake tokens).
    - Overrides get_session, get_current_user, get_current_tenant_id, get_redis
      so route handlers receive predictable test inputs.
    - Wires app.state.http_client to FakeModelserverTransport so POST /classify
      never hits a real modelserver.

    The default authenticated user is `tenant_admin` (Tenant A).
    For manager-role tests, use the `manager_client` fixture below.
    """
    from app.dependencies import (
        get_current_tenant_id,
        get_current_user,
        get_redis,
        get_session,
    )
    from app.main import app as fastapi_app

    # ── Bypass the real lifespan ───────────────────────────────────────────────
    # Starlette stores the lifespan as app.router.lifespan_context.
    # We swap it with a no-op so Vault/DB/Redis connect is skipped entirely.
    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    original_lifespan = fastapi_app.router.lifespan_context
    fastapi_app.router.lifespan_context = _noop_lifespan

    # ── Populate app.state ────────────────────────────────────────────────────
    fastapi_app.state.widget_signing_key  = "test-signing-key-32-bytes-padding!!"
    fastapi_app.state.modelserver_token   = "test-modelserver-token"
    fastapi_app.state.guardrails_token    = "test-guardrails-token"
    fastapi_app.state.llm_api_key         = "test-llm-key"
    fastapi_app.state.redis               = fake_redis
    fastapi_app.state.session_factory     = async_sessionmaker(
        test_engine, expire_on_commit=False
    )
    fastapi_app.state.http_client = AsyncClient(
        transport=FakeModelserverTransport(),
        base_url="http://modelserver",
    )

    # ── Dependency overrides ───────────────────────────────────────────────────
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_session]             = _session_override
    fastapi_app.dependency_overrides[get_redis]               = lambda: fake_redis
    fastapi_app.dependency_overrides[get_current_user]        = lambda: tenant_admin
    fastapi_app.dependency_overrides[get_current_tenant_id]   = lambda: TENANT_A_ID

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as c:
        yield c

    # ── Teardown ───────────────────────────────────────────────────────────────
    fastapi_app.dependency_overrides.clear()
    fastapi_app.router.lifespan_context = original_lifespan
    await fastapi_app.state.http_client.aclose()


@pytest.fixture
async def manager_client(test_engine, db_session, fake_redis, tenant_manager):
    """
    Same as `client` but authenticated as tenant_manager with no tenant context.
    Use for tests that hit /api/v1/platform/tenants endpoints.
    """
    from app.dependencies import (
        get_current_tenant_id,
        get_current_user,
        get_redis,
        get_session,
    )
    from app.main import app as fastapi_app

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    original_lifespan = fastapi_app.router.lifespan_context
    fastapi_app.router.lifespan_context = _noop_lifespan

    fastapi_app.state.widget_signing_key  = "test-signing-key-32-bytes-padding!!"
    fastapi_app.state.modelserver_token   = "test-modelserver-token"
    fastapi_app.state.guardrails_token    = "test-guardrails-token"
    fastapi_app.state.llm_api_key         = "test-llm-key"
    fastapi_app.state.redis               = fake_redis
    fastapi_app.state.session_factory     = async_sessionmaker(
        test_engine, expire_on_commit=False
    )
    fastapi_app.state.http_client = AsyncClient(
        transport=FakeModelserverTransport(),
        base_url="http://modelserver",
    )

    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_session]             = _session_override
    fastapi_app.dependency_overrides[get_redis]               = lambda: fake_redis
    fastapi_app.dependency_overrides[get_current_user]        = lambda: tenant_manager
    fastapi_app.dependency_overrides[get_current_tenant_id]   = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as c:
        yield c

    fastapi_app.dependency_overrides.clear()
    fastapi_app.router.lifespan_context = original_lifespan
    await fastapi_app.state.http_client.aclose()
