# Owner A — backend/app/models/lead.py
#
# A lead is created when the agent's capture_lead tool fires.
# Represents a visitor who expressed buying intent and left contact details.
# Owner B writes the lead_repo.py and capture_lead tool that insert rows here.
# Owner D's admin UI reads these via GET /api/v1/admin/leads (paginated).

import uuid
from typing import Optional

from sqlalchemy import Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Lead(Base, TenantMixin, TimestampMixin):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # The chat session that produced this lead
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    visitor_name: Mapped[str] = mapped_column(String, nullable=False)

    # Email address or E.164 phone number — validated in capture_lead tool
    contact: Mapped[str] = mapped_column(String, nullable=False)

    # What the visitor wants — summarised by the agent before calling the tool
    intent: Mapped[str] = mapped_column(Text, nullable=False)

    # Classifier confidence at the time the lead was captured — useful for quality filtering
    classifier_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
