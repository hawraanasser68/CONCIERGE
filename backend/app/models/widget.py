# Owner A — backend/app/models/widget.py
#
# A widget is an embeddable chat button a tenant places on their website.
# Each tenant can have multiple widgets with different configs (greeting, persona, origins).
# allowed_origins is the security gate for the token exchange:
# a request from an origin not in this list gets a 403 and the loader silently does nothing.

import uuid

from sqlalchemy import ARRAY, Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Widget(Base, TenantMixin, TimestampMixin):
    __tablename__ = "widgets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)

    # List of allowed origin URLs e.g. ["https://acme.com", "https://app.acme.com"]
    # Owner D's token exchange validates request Origin against this list → 403 if not found
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )

    greeting: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="Hi! How can I help you today?",
    )
    persona_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="Assistant",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
