# Owner A — backend/app/tenancy/manager.py
#
# Tenant lifecycle: provisioning and GDPR erasure.
# Called only by manager.py route — require_role(Role.tenant_manager) enforced there.
#
# Provisioning is atomic: tenant row + agent_config seed + audit log in one transaction.
# Erasure sets status='erasing' first so a second concurrent call fails fast (409).

import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException
from minio import Minio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_config import AgentConfig
from app.models.chunk import Chunk
from app.models.cms import CmsPage
from app.models.escalation import Escalation
from app.models.lead import Lead
from app.models.tenant import Tenant
from app.models.tenant_costs import TenantCosts
from app.models.user import User
from app.models.widget import Widget
from app.repositories.agent_config_repo import agent_config_repo
from app.repositories.tenant_repo import tenant_repo
from app.tenancy.audit import write_audit_log

log = structlog.get_logger()


async def provision_tenant(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    actor_id: uuid.UUID,
) -> dict:
    """
    Creates a new tenant with default agent_config in one atomic transaction.
    Returns {"tenant_id": uuid, "invite_token": str}.

    The invite_token is a one-time UUID the manager gives to the first admin,
    who uses it as proof-of-invite when calling POST /api/v1/auth/register.
    """
    existing = await tenant_repo.get_by_slug(session, slug)
    if existing:
        raise HTTPException(status_code=409, detail=f"Slug '{slug}' is already taken")

    tenant = await tenant_repo.create(session, slug=slug, name=name)
    await agent_config_repo.create_defaults(session, tenant.id)

    invite_token = str(uuid.uuid4())

    await write_audit_log(
        session,
        actor_id=actor_id,
        actor_role="tenant_manager",
        action="tenant.create",
        target_id=tenant.id,
        target_type="tenant",
        metadata={"slug": slug, "name": name},
    )

    log.info("tenant_provisioned", tenant_id=str(tenant.id), slug=slug)

    return {"tenant_id": tenant.id, "invite_token": invite_token}


async def erase_tenant(
    session: AsyncSession,
    redis: aioredis.Redis,
    minio: Minio,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    """
    GDPR right-to-erasure. Deletes all tenant data in FK-safe order, then marks erased.

    Sets status='erasing' first so concurrent calls get a 409.
    Audit log rows are NEVER deleted — they are the compliance trail.
    """
    tenant = await tenant_repo.get_by_id(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status == "erasing":
        raise HTTPException(status_code=409, detail="Erasure already in progress")
    if tenant.status == "erased":
        raise HTTPException(status_code=409, detail="Tenant already erased")

    # Mark erasing before doing any work — prevents concurrent erasure
    await tenant_repo.update_status(session, tenant, "erasing")

    await write_audit_log(
        session,
        actor_id=actor_id,
        actor_role="tenant_manager",
        action="tenant.erase_started",
        target_id=tenant_id,
        target_type="tenant",
    )

    # Delete in FK-safe order (children before parents)
    for model in [Chunk, Lead, Escalation, CmsPage, AgentConfig, Widget, TenantCosts, User]:
        await session.execute(
            delete(model).where(model.tenant_id == tenant_id)
        )

    tenant.status = "erased"
    tenant.erased_at = datetime.now(timezone.utc)
    session.add(tenant)

    # Audit log written before final commit so it's in the same transaction
    await write_audit_log(
        session,
        actor_id=actor_id,
        actor_role="tenant_manager",
        action="tenant.erase_complete",
        target_id=tenant_id,
        target_type="tenant",
    )

    await session.commit()

    # Flush Redis keys after commit — non-critical if this fails
    try:
        pattern_conv = f"conversation:{tenant_id}:*"
        pattern_rate = f"ratelimit:{tenant_id}:*"
        for pattern in [pattern_conv, pattern_rate]:
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
    except Exception:
        log.warning("redis_flush_failed_after_erase", tenant_id=str(tenant_id))

    # Purge MinIO blobs under tenants/{tenant_id}/ — non-critical if bucket absent
    try:
        bucket = "concierge"
        prefix = f"tenants/{tenant_id}/"
        objects = minio.list_objects(bucket, prefix=prefix, recursive=True)
        object_names = [obj.object_name for obj in objects]
        if object_names:
            for name in object_names:
                minio.remove_object(bucket, name)
            log.info("minio_blobs_purged", tenant_id=str(tenant_id), count=len(object_names))
    except Exception:
        log.warning("minio_purge_failed_after_erase", tenant_id=str(tenant_id))

    log.info("tenant_erased", tenant_id=str(tenant_id))
