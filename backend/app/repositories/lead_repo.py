# Owner B — backend/app/repositories/lead_repo.py
#
# Insert and paginate lead rows created by the capture_lead tool.
# Column mapping: Lead.visitor_name ← name argument — never write Lead(name=...).
# See INTERFACES.md §5 for the mapping rationale (model column ≠ LLM schema field).

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.repositories.base import TenantRepository


class LeadRepository(TenantRepository[Lead]):
    model = Lead

    async def insert(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        session_id: str,
        visitor_name: str,      # column is visitor_name, not name — see INTERFACES.md
        contact: str,
        intent: str,
        classifier_score: Optional[float] = None,
    ) -> Lead:
        lead = Lead(
            tenant_id=tenant_id,
            session_id=session_id,
            visitor_name=visitor_name,
            contact=contact,
            intent=intent,
            classifier_score=classifier_score,
        )
        session.add(lead)
        await session.flush()
        await session.refresh(lead)
        return lead

    async def paginated_list(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Lead]:
        stmt = (
            self.scoped(tenant_id)
            .order_by(Lead.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


lead_repo = LeadRepository()
