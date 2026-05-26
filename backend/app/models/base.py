# Owner A — backend/app/models/base.py
#
# Shared base classes for all SQLAlchemy models.
# Every model in this package inherits from Base.
# Tenant-scoped models also inherit TenantMixin.

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base. All models inherit from this."""
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TenantMixin:
    """
    Adds tenant_id FK to any tenant-scoped model.

    Belt-and-suspenders isolation:
    - RLS policy filters rows via the session variable app.tenant_id
    - Every query also carries an explicit .filter(Model.tenant_id == tenant_id)
    Both must agree; a mismatch is caught in the integration test (A-047).
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
