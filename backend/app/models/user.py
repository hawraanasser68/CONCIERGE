# Owner A — backend/app/models/user.py
#
# User model — integrates with fastapi-users.
# tenant_id is nullable: NULL means the user is a tenant_manager (platform-level role).
# tenant_admin and member users always have a non-null tenant_id.

import uuid
from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """
    Extends fastapi-users' base table with role and tenant_id.
    fastapi-users provides: id, email, hashed_password, is_active, is_superuser, is_verified.
    We add: tenant_id, role, created_at.
    """

    __tablename__ = "users"

    # NULL for tenant_manager — they operate across all tenants, not within one
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="member",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('tenant_manager', 'tenant_admin', 'member')",
            name="users_role_check",
        ),
    )
