# Owner A — backend/app/routes/tenant_admin.py
#
# Admin endpoints for tenant_admin role. Owner A owns this file entirely.
# Owner D's Streamlit admin UI calls every endpoint here.
#
# Endpoints:
#   Widgets:      GET/POST /api/v1/admin/widgets
#                 GET/PUT/DELETE /api/v1/admin/widgets/{id}
#                 PATCH /api/v1/admin/widgets/{id}/toggle
#   Leads:        GET /api/v1/admin/leads  (paginated, read-only — Owner B writes rows)
#   Escalations:  GET /api/v1/admin/escalations  (read-only — Owner B writes rows)
#   Agent config: GET/PUT /api/v1/admin/agent-config

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.roles import Role, require_role
from app.dependencies import get_current_tenant_id, get_session
from app.models.escalation import Escalation
from app.models.lead import Lead
from app.repositories.agent_config_repo import agent_config_repo
from app.repositories.widget_repo import widget_repo
from app.schemas.lead import LeadResponse
from app.schemas.widget import WidgetCreate, WidgetResponse, WidgetUpdate
from app.tenancy.audit import write_audit_log

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_admin = require_role(Role.tenant_admin)


# ── Inline schemas for escalation and agent-config ────────────────────────────
# Not in schemas/ because they're only used in this file.

class EscalationResponse(BaseModel):
    id: uuid.UUID
    session_id: str
    reason: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentConfigResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    persona_name: str
    persona_description: str
    enabled_tools: List[str]
    blocked_topics: List[str]
    allowed_topics: List[str]
    max_tool_iterations: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentConfigUpdate(BaseModel):
    """All fields optional — supports partial updates."""
    persona_name: Optional[str] = None
    persona_description: Optional[str] = None
    enabled_tools: Optional[List[str]] = None
    blocked_topics: Optional[List[str]] = None
    allowed_topics: Optional[List[str]] = None
    max_tool_iterations: Optional[int] = None


# ── Widgets ───────────────────────────────────────────────────────────────────

@router.get("/widgets", response_model=list[WidgetResponse])
async def list_widgets(
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    return await widget_repo.list_all(session, tenant_id)


@router.post("/widgets", response_model=WidgetResponse, status_code=201)
async def create_widget(
    body: WidgetCreate,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    widget = await widget_repo.create(
        session,
        tenant_id=tenant_id,
        name=body.name,
        allowed_origins=body.allowed_origins,
        greeting=body.greeting,
        persona_name=body.persona_name,
    )
    await write_audit_log(
        session,
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="widget.create",
        target_id=widget.id,
        target_type="widget",
        metadata={"name": body.name},
    )
    await session.commit()
    return widget


@router.get("/widgets/{widget_id}", response_model=WidgetResponse)
async def get_widget(
    widget_id: uuid.UUID,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    widget = await widget_repo.get_by_id(session, tenant_id, widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    return widget


@router.put("/widgets/{widget_id}", response_model=WidgetResponse)
async def update_widget(
    widget_id: uuid.UUID,
    body: WidgetUpdate,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    widget = await widget_repo.get_by_id(session, tenant_id, widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    widget = await widget_repo.update(
        session,
        widget,
        name=body.name,
        allowed_origins=body.allowed_origins,
        greeting=body.greeting,
        persona_name=body.persona_name,
    )
    await write_audit_log(
        session,
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="widget.update",
        target_id=widget.id,
        target_type="widget",
    )
    await session.commit()
    return widget


@router.delete("/widgets/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: uuid.UUID,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    widget = await widget_repo.get_by_id(session, tenant_id, widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    await write_audit_log(
        session,
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="widget.delete",
        target_id=widget.id,
        target_type="widget",
        metadata={"name": widget.name},
    )
    await widget_repo.delete(session, widget)
    await session.commit()


@router.patch("/widgets/{widget_id}/toggle", response_model=WidgetResponse)
async def toggle_widget(
    widget_id: uuid.UUID,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    """Flips is_active. Owner D's admin UI calls this to enable/disable a widget."""
    widget = await widget_repo.get_by_id(session, tenant_id, widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    widget = await widget_repo.toggle_active(session, widget)
    await write_audit_log(
        session,
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="widget.toggled",
        target_id=widget.id,
        target_type="widget",
        metadata={"is_active": widget.is_active},
    )
    await session.commit()
    return widget


# ── Leads (read-only — Owner B's capture_lead tool writes rows) ───────────────

@router.get("/leads", response_model=list[LeadResponse])
async def list_leads(
    page: int = 1,
    page_size: int = 20,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    """Paginated lead list. page and page_size are query params."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    offset = (page - 1) * page_size
    result = await session.execute(
        select(Lead)
        .where(Lead.tenant_id == tenant_id)
        .order_by(Lead.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return list(result.scalars().all())


# ── Escalations (read-only — Owner B's escalate tool writes rows) ─────────────

@router.get("/escalations", response_model=list[EscalationResponse])
async def list_escalations(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Lists escalations for the tenant. Optional ?status=open|resolved|closed filter.
    Owner D's admin UI uses this to show the support queue.
    """
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    offset = (page - 1) * page_size

    stmt = (
        select(Escalation)
        .where(Escalation.tenant_id == tenant_id)
        .order_by(Escalation.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if status:
        stmt = stmt.where(Escalation.status == status)

    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Agent config ──────────────────────────────────────────────────────────────

@router.get("/agent-config", response_model=AgentConfigResponse)
async def get_agent_config(
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    config = await agent_config_repo.get_for_tenant(session, tenant_id)
    if not config:
        raise HTTPException(status_code=404, detail="Agent config not found")
    return config


@router.put("/agent-config", response_model=AgentConfigResponse)
async def update_agent_config(
    body: AgentConfigUpdate,
    current_user=Depends(_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Partial update — only provided fields are changed.
    Owner B reads agent_config on every chat request via agent_config_repo.
    """
    config = await agent_config_repo.get_for_tenant(session, tenant_id)
    if not config:
        raise HTTPException(status_code=404, detail="Agent config not found")
    config = await agent_config_repo.update(
        session,
        config,
        persona_name=body.persona_name,
        persona_description=body.persona_description,
        enabled_tools=body.enabled_tools,
        blocked_topics=body.blocked_topics,
        allowed_topics=body.allowed_topics,
        max_tool_iterations=body.max_tool_iterations,
    )
    await write_audit_log(
        session,
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="agent_config.update",
        target_id=config.id,
        target_type="agent_config",
    )
    await session.commit()
    return config
