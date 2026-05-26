# Owner A — backend/app/repositories/agent_config_repo.py
#
# AgentConfig is one-row-per-tenant. A creates the seed row during tenant provisioning.
# Owner B reads this in agent.py to load persona + tool settings per request.
# Owner D's admin UI edits it via GET/PUT /api/v1/admin/agent-config.

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_config import AgentConfig
from app.repositories.base import TenantRepository


class AgentConfigRepository(TenantRepository[AgentConfig]):
    model = AgentConfig

    async def get_for_tenant(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> AgentConfig | None:
        """Returns the single config row for a tenant."""
        result = await session.execute(self.scoped(tenant_id))
        return result.scalar_one_or_none()

    async def create_defaults(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> AgentConfig:
        """Seeds the default AgentConfig row during tenant provisioning."""
        config = AgentConfig(tenant_id=tenant_id)
        session.add(config)
        await session.flush()
        return config

    async def update(
        self,
        session: AsyncSession,
        config: AgentConfig,
        *,
        persona_name: Optional[str] = None,
        persona_description: Optional[str] = None,
        enabled_tools: Optional[list[str]] = None,
        blocked_topics: Optional[list[str]] = None,
        allowed_topics: Optional[list[str]] = None,
        max_tool_iterations: Optional[int] = None,
    ) -> AgentConfig:
        if persona_name is not None:
            config.persona_name = persona_name
        if persona_description is not None:
            config.persona_description = persona_description
        if enabled_tools is not None:
            config.enabled_tools = enabled_tools
        if blocked_topics is not None:
            config.blocked_topics = blocked_topics
        if allowed_topics is not None:
            config.allowed_topics = allowed_topics
        if max_tool_iterations is not None:
            config.max_tool_iterations = max_tool_iterations
        session.add(config)
        await session.flush()
        return config


agent_config_repo = AgentConfigRepository()
