# Owner A — backend/app/models/escalation.py
#
# Created when the agent's escalate tool fires — visitor needs a human agent.
# Owner B writes escalation_repo.py and the escalate tool that insert rows here.
# Owner D's admin UI reads these via GET /api/v1/admin/escalations.

import uuid

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Escalation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Why the visitor needs a human — populated by the agent before calling the tool
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Lifecycle: open → resolved | closed
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved', 'closed')",
            name="escalations_status_check",
        ),
    )
