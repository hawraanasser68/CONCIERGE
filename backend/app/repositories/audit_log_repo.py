# Owner A — backend/app/repositories/audit_log_repo.py
#
# Read path for audit_log. Write path lives in tenancy/audit.py (append-only).
# Only tenant_manager can read audit logs via the platform route.
# Rows for erased tenants are never deleted — they are the compliance trail.

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogRepository:
    """No TenantRepository mixin — audit_log has no RLS and no tenant_id FK requirement."""

    async def list_by_actor(
        self,
        session: AsyncSession,
        actor_id: uuid.UUID,
        limit: int = 100,
    ) -> list[AuditLog]:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.actor_id == actor_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_target(
        self,
        session: AsyncSession,
        target_id: uuid.UUID,
        limit: int = 100,
    ) -> list[AuditLog]:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.target_id == target_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


audit_log_repo = AuditLogRepository()
