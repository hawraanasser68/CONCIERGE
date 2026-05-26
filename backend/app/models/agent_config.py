# Owner A — backend/app/models/agent_config.py
#
# One row per tenant — stores the AI agent's persona and tool configuration.
# Created automatically during tenant provisioning alongside the tenant row.
# Owner B reads this in agent.py to load persona + tool settings per request.
# Owner D's admin UI exposes GET/PUT /api/v1/admin/agent-config to edit this.

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class AgentConfig(Base, TenantMixin):
    __tablename__ = "agent_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    persona_name: Mapped[str] = mapped_column(String, nullable=False, default="Assistant")
    persona_description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Which tools the agent is allowed to call for this tenant.
    # Platform rails (injection, jailbreak) are always enforced regardless of this list.
    enabled_tools: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=lambda: ["rag_search", "capture_lead", "escalate"],
    )

    # Topics the agent must refuse to discuss for this tenant
    blocked_topics: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    # Topics the agent is restricted to (empty = no restriction beyond platform rails)
    allowed_topics: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    # Tenant-configurable cap. Owner B's agent.py uses min(this, 10) — 10 is the absolute ceiling.
    max_tool_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # One config row per tenant — enforced at the DB level
        UniqueConstraint("tenant_id", name="agent_config_tenant_id_key"),
    )
