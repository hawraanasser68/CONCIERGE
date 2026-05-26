# Owner A — backend/app/tenancy/audit.py
#
# Append-only audit log writer. Called after every sensitive action.
# Audit rows for erased tenants are NEVER deleted — they are the compliance trail.
# No update or delete path exists anywhere in the codebase.

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

log = structlog.get_logger()


async def write_audit_log(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor_role: str,
    action: str,
    target_id: uuid.UUID | None = None,
    target_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Appends one row to audit_log. Always awaited inline — never fire-and-forget.
    Flushed as part of the same transaction as the action it records.

    Example actions: "tenant.create", "tenant.erase_started", "widget.create",
                     "agent_config.update", "tenant.erase_complete"
    """
    entry = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_id=target_id,
        target_type=target_type,
        metadata_=metadata,
    )
    session.add(entry)
    await session.flush()   # write within the current transaction, don't commit yet

    log.info(
        "audit_log_written",
        action=action,
        actor_id=str(actor_id),
        target_id=str(target_id) if target_id else None,
    )
