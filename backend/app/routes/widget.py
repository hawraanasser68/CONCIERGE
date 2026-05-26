# Owner D — backend/app/routes/widget.py
#
# Public, no-auth endpoints called by the widget loader and iframe app.
# Replaces Owner A's Day-1 501 stub. Auto-discovered by main.py.
#
# Endpoints:
#   POST /api/v1/widget/token           — exchange (widget_id, origin) for a signed JWT
#   GET  /api/v1/widget/{id}/config     — public widget config (greeting, persona, theme)
#
# Token-exchange request/response schemas are defined inline below because they are
# only used here. The widget admin CRUD schemas live in app/schemas/widget.py (Owner A).

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.widget_token import TTL_SECONDS, sign_widget_jwt
from app.dependencies import get_session
from app.models.widget import Widget

router = APIRouter(prefix="/api/v1/widget", tags=["widget"])


# ── Schemas (route-local) ─────────────────────────────────────────────────────

class WidgetTokenRequest(BaseModel):
    widget_id: uuid.UUID
    origin: str


class WidgetTokenResponse(BaseModel):
    token: str
    session_id: str
    expires_at: datetime


class WidgetTheme(BaseModel):
    primary_color: str


class WidgetConfigResponse(BaseModel):
    greeting: str
    persona_name: str
    theme: WidgetTheme


# ── POST /token — issue a widget session JWT ─────────────────────────────────

@router.post("/token", response_model=WidgetTokenResponse)
async def exchange_widget_token(
    body: WidgetTokenRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> WidgetTokenResponse:
    """
    Exchanges a public widget_id + the embedding site's origin for a short-lived JWT.
    The origin check here (server-side) is the real guard — CORS is browser-only.
    Inactive and non-existent widgets share the same 404 response to avoid enumeration.
    """
    widget = await session.get(Widget, body.widget_id)
    if widget is None or not widget.is_active:
        raise HTTPException(status_code=404, detail="Widget not found")

    if body.origin not in widget.allowed_origins:
        raise HTTPException(
            status_code=403,
            detail="Origin not allowed",
            headers={"X-Error-Code": "ORIGIN_BLOCKED"},
        )

    session_id = str(uuid.uuid4())
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=TTL_SECONDS)

    token = sign_widget_jwt(
        signing_key=request.app.state.widget_signing_key,
        tenant_id=str(widget.tenant_id),
        widget_id=str(widget.id),
        origin=body.origin,
        session_id=session_id,
    )

    return WidgetTokenResponse(
        token=token,
        session_id=session_id,
        expires_at=expires_at,
    )


# ── GET /{widget_id}/config — public, read-only ───────────────────────────────

@router.get("/{widget_id}/config", response_model=WidgetConfigResponse)
async def get_widget_config(
    widget_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> WidgetConfigResponse:
    """
    Returns the public-facing widget config: greeting, persona name, and theme.
    Used by the iframe app at load time to render the initial chat surface.
    """
    widget = await session.get(Widget, widget_id)
    if widget is None or not widget.is_active:
        raise HTTPException(status_code=404, detail="Widget not found")

    return WidgetConfigResponse(
        greeting=widget.greeting,
        persona_name=widget.persona_name,
        theme=WidgetTheme(primary_color="#0066cc"),
    )
