# Owner A — backend/app/models/audit_log.py
#
# Append-only compliance trail. No RLS — only tenant_manager can read via route check.
# Rows for erased tenants are NEVER deleted — they are the GDPR audit evidence.
# No update path exists anywhere in the codebase.

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """
    No TenantMixin — audit_log is not tenant-scoped.
    actor_id can be a tenant_manager (no tenant) or a tenant_admin (has tenant).
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)

    # Examples: "tenant.create", "tenant.erase_started", "tenant.erase_complete",
    # "widget.create", "agent_config.update"
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # The entity being acted on (e.g. the tenant_id being erased)
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Arbitrary context — diff snapshots, IP address, request ID, etc.
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
