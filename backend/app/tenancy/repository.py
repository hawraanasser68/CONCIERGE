# Owner A — backend/app/tenancy/repository.py
#
# Base mixin for all tenant-scoped repositories.
# Every concrete repo inherits TenantRepository and uses scoped() to build queries.
#
# Belt-and-suspenders: explicit WHERE tenant_id = :tid in every query (belt)
# + Postgres RLS policy filtering via app.tenant_id session var (suspenders).
# Both must agree. A query that bypasses this mixin is a cross-tenant data leak.

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):
    """
    Base class for all tenant-scoped repositories.

    Usage:
        class WidgetRepository(TenantRepository[Widget]):
            model = Widget

            async def get_by_id(self, session, tenant_id, widget_id):
                stmt = self.scoped(tenant_id).where(Widget.id == widget_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
    """

    model: type[ModelT]

    def scoped(self, tenant_id: uuid.UUID):
        """
        Returns a SELECT statement pre-filtered by tenant_id.
        Always use this as the starting point — never write raw select(Model) in a repo.
        """
        return select(self.model).where(self.model.tenant_id == tenant_id)

    async def get_by_id(
        self, session: AsyncSession, tenant_id: uuid.UUID, row_id: uuid.UUID
    ) -> ModelT | None:
        stmt = self.scoped(tenant_id).where(self.model.id == row_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> list[ModelT]:
        stmt = self.scoped(tenant_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())
