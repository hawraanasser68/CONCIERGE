# Owner A — backend/app/repositories/tenant_repo.py
#
# Tenant CRUD. No RLS applies here — tenants is not an RLS-protected table.
# Route-level require_role(Role.tenant_manager) guards all callers.

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


class TenantRepository:
    """
    Not a TenantRepository (mixin) subclass because tenants has no tenant_id column.
    Managed directly by the tenant_manager role only.
    """

    async def get_by_id(self, session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
        return await session.get(Tenant, tenant_id)

    async def get_by_slug(self, session: AsyncSession, slug: str) -> Tenant | None:
        result = await session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def list_all(self, session: AsyncSession) -> list[Tenant]:
        result = await session.execute(select(Tenant))
        return list(result.scalars().all())

    async def create(
        self, session: AsyncSession, *, slug: str, name: str
    ) -> Tenant:
        tenant = Tenant(slug=slug, name=name)
        session.add(tenant)
        await session.flush()
        return tenant

    async def update_status(
        self, session: AsyncSession, tenant: Tenant, status: str
    ) -> Tenant:
        tenant.status = status
        session.add(tenant)
        await session.flush()
        return tenant


tenant_repo = TenantRepository()
