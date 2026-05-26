# Owner B — backend/app/repositories/escalation_repo.py
#
# Insert escalation rows and manage their lifecycle (open → resolved → closed).
# Column mapping: Escalation.session_id ← conversation_id argument.
# See INTERFACES.md §5 — the LLM schema field name differs from the model column.

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import Escalation
from app.repositories.base import TenantRepository


class EscalationRepository(TenantRepository[Escalation]):
    model = Escalation

    async def insert(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        session_id: str,        # column is session_id — conversation_id maps here (INTERFACES.md)
        reason: str,
    ) -> Escalation:
        escalation = Escalation(
            tenant_id=tenant_id,
            session_id=session_id,
            reason=reason,
            status="open",
        )
        session.add(escalation)
        await session.flush()
        await session.refresh(escalation)
        return escalation

    async def update_status(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        escalation_id: uuid.UUID,
        status: str,
    ) -> Escalation | None:
        escalation = await self.get_by_id(session, tenant_id, escalation_id)
        if escalation is None:
            return None
        escalation.status = status
        session.add(escalation)
        await session.flush()
        await session.refresh(escalation)
        return escalation


escalation_repo = EscalationRepository()
