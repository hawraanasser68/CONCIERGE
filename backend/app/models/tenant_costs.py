# Owner A — backend/app/models/tenant_costs.py
#
# Daily cost attribution per tenant. One row per (tenant_id, date).
# Owner A's cost_meter.py upserts into this table after every LLM/embed call.
# tenant_manager can read aggregate costs via the manager route.

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class TenantCosts(Base, TenantMixin):
    __tablename__ = "tenant_costs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # One row per tenant per calendar day (UTC)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    llm_tokens_in: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    llm_tokens_out: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    embed_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    classify_calls: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Upsert key — cost_meter.py uses ON CONFLICT (tenant_id, date) DO UPDATE
        UniqueConstraint("tenant_id", "date", name="tenant_costs_tenant_date_key"),
    )
