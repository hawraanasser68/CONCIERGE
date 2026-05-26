# Owner A — backend/app/models/tenant.py
#
# The root entity of the multi-tenant system.
# No tenant_id FK — this IS the tenant.
# No RLS — access is controlled by require_role(Role.tenant_manager) at the route level.

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)

    # Status lifecycle: active → suspended → erasing → erased
    # get_current_tenant_id checks status == 'active' on every request,
    # so suspending a tenant instantly denies all existing JWTs.
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="active",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    erased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'erasing', 'erased')",
            name="tenants_status_check",
        ),
    )
