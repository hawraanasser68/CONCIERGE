# Owner A — backend/app/dependencies.py
#
# FastAPI dependencies used across the entire backend.
# Every route that needs a DB session, the current user, or a tenant context
# imports from here. Nothing reads os.environ or app.state directly in routes.
#
# Dependency chain for a typical tenant_admin request:
#   get_session → get_current_user → get_current_tenant_id (sets RLS) → route handler

import uuid
from typing import AsyncGenerator

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.widget_token import verify_widget_jwt
# Safe top-level import: auth/users.py uses request.app.state directly, not dependencies.py
from app.auth.users import fastapi_users
from app.models.tenant import Tenant
from app.models.widget import Widget
from app.tenancy.rls import set_manager_rls, set_tenant_rls

log = structlog.get_logger()

# Reusable fastapi-users dependency
_current_user_dep = fastapi_users.current_user(active=True)


# ── Database session ──────────────────────────────────────────────────────────

async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yields an async DB session scoped to the request."""
    async with request.app.state.session_factory() as session:
        yield session


# ── Redis ─────────────────────────────────────────────────────────────────────

async def get_redis(request: Request) -> aioredis.Redis:
    """Returns the shared Redis connection pool."""
    return request.app.state.redis


# ── Authenticated user (fastapi-users) ───────────────────────────────────────

async def get_current_user(user=Depends(_current_user_dep)):
    """Returns the authenticated active user from the Bearer JWT."""
    return user


# ── Tenant context (the critical dependency) ─────────────────────────────────

async def get_current_tenant_id(
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
) -> uuid.UUID | None:
    """
    Extracts tenant_id from the authenticated user, validates the tenant is active,
    and sets the Postgres RLS session variable for this transaction.

    SECURITY: tenant_id comes exclusively from the verified JWT — never from
    request body, query params, or any client-supplied field.

    Returns None for tenant_manager role (they have no tenant_id).
    """
    if current_user.role == "tenant_manager":
        await set_manager_rls(session)
        return None

    if current_user.tenant_id is None:
        raise HTTPException(status_code=403, detail="User has no tenant assigned")

    # Verify tenant is active on every request — suspending a tenant instantly
    # denies all their users without needing to revoke individual tokens.
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(status_code=403, detail="Tenant not found")
    if tenant.status != "active":
        raise HTTPException(status_code=403, detail=f"Tenant is {tenant.status}")

    await set_tenant_rls(session, current_user.tenant_id)
    return current_user.tenant_id


# ── Widget session (chat requests from the widget) ────────────────────────────

async def get_widget_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_session_id: str = Header(..., alias="X-Session-Id"),
) -> dict:
    """
    Validates the widget JWT on every chat request.
    Implements the 7-step validation chain from INTERFACES.md.
    Returns the decoded payload dict (tenant_id, widget_id, session_id, origin).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header[7:]
    signing_key = request.app.state.widget_signing_key

    # Steps 1-3: signature, expiry, type
    payload = verify_widget_jwt(token, signing_key)

    # Step 4: X-Session-Id header must match the JWT claim (prevents session injection)
    if payload.get("session_id") != x_session_id:
        raise HTTPException(status_code=400, detail="Session ID mismatch")

    # Step 5: widget must exist and be active
    widget_id = uuid.UUID(payload["widget_id"])
    widget = await session.get(Widget, widget_id)
    if not widget or not widget.is_active:
        raise HTTPException(status_code=401, detail="Widget not found or inactive")

    # Step 6: incoming Origin must be in the widget's allowed_origins allowlist.
    # We check the DB allowlist here (not the JWT origin claim) because chat requests
    # originate from the widget's serving domain, which differs from the host page
    # origin stored in the JWT at token-exchange time. The JWT claim is kept for
    # audit purposes only.
    incoming_origin = request.headers.get("Origin", "")
    if incoming_origin not in widget.allowed_origins:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    # Step 7: tenant_id in JWT must match the widget's actual tenant
    if str(widget.tenant_id) != payload.get("tenant_id"):
        raise HTTPException(status_code=401, detail="Token tenant mismatch")

    # Verify tenant is active and set RLS
    result = await session.execute(
        select(Tenant).where(Tenant.id == widget.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=403, detail="Tenant is not active")

    await set_tenant_rls(session, widget.tenant_id)
    return payload
