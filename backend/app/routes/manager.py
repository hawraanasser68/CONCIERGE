# Owner A — backend/app/routes/manager.py
#
# Platform management endpoints for the tenant_manager role.
# Tenant managers provision new tenants and trigger GDPR erasure.
# No tenant-scoped RLS applies here — tenants table has no RLS.
#
# Endpoints:
#   GET    /api/v1/platform/tenants           → list all tenants
#   POST   /api/v1/platform/tenants           → provision new tenant + agent_config seed
#   GET    /api/v1/platform/tenants/{id}      → get a single tenant
#   DELETE /api/v1/platform/tenants/{id}      → GDPR erasure

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.roles import Role, require_role
from app.dependencies import get_redis, get_session
from app.repositories.tenant_repo import tenant_repo
from app.schemas.tenant import TenantCreate, TenantCreateResponse, TenantResponse
from app.tenancy.manager import erase_tenant, provision_tenant

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])

_manager = require_role(Role.tenant_manager)


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    current_user=Depends(_manager),
    session: AsyncSession = Depends(get_session),
):
    """Returns all tenants regardless of status. Manager-only."""
    return await tenant_repo.list_all(session)


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    current_user=Depends(_manager),
    session: AsyncSession = Depends(get_session),
):
    from fastapi import HTTPException
    tenant = await tenant_repo.get_by_id(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("/tenants", response_model=TenantCreateResponse, status_code=201)
async def create_tenant(
    body: TenantCreate,
    current_user=Depends(_manager),
    session: AsyncSession = Depends(get_session),
):
    """
    Provisions a new tenant:
    1. Validates slug uniqueness
    2. Creates tenant row
    3. Seeds agent_config defaults
    4. Writes audit log
    5. Returns tenant_id + one-time invite_token for the first admin
    """
    result = await provision_tenant(
        session,
        slug=body.slug,
        name=body.name,
        actor_id=current_user.id,
    )
    await session.commit()
    return result


@router.delete("/tenants/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user=Depends(_manager),
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
):
    """
    GDPR right-to-erasure. Deletes all tenant data in FK-safe order.
    Sets status='erasing' first — a second concurrent call gets 409.
    audit_log rows for this tenant are retained (compliance trail).
    """
    await erase_tenant(
        session,
        redis,
        tenant_id=tenant_id,
        actor_id=current_user.id,
    )
