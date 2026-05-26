# Owner B — backend/app/repositories/cms_page_repo.py
#
# CRUD repository for CMS pages. Enforces the (tenant_id, slug) uniqueness
# constraint at the application layer — callers must catch IntegrityError and
# return HTTP 409. update() and delete() scope reads to tenant_id before
# mutating so cross-tenant modifications are architecturally impossible.

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cms import CmsPage
from app.repositories.base import TenantRepository


class CmsPageRepository(TenantRepository[CmsPage]):
    model = CmsPage

    async def create(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        title: str,
        slug: str,
        content: str,
        is_published: bool = False,
    ) -> CmsPage:
        page = CmsPage(
            tenant_id=tenant_id,
            title=title,
            slug=slug,
            content=content,
            is_published=is_published,
        )
        session.add(page)
        await session.flush()
        await session.refresh(page)
        return page

    async def update(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        page_id: uuid.UUID,
        *,
        title: str | None = None,
        slug: str | None = None,
        content: str | None = None,
        is_published: bool | None = None,
    ) -> CmsPage | None:
        page = await self.get_by_id(session, tenant_id, page_id)
        if page is None:
            return None
        if title is not None:
            page.title = title
        if slug is not None:
            page.slug = slug
        if content is not None:
            page.content = content
        if is_published is not None:
            page.is_published = is_published
        session.add(page)
        await session.flush()
        await session.refresh(page)
        return page

    async def delete(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        page_id: uuid.UUID,
    ) -> bool:
        page = await self.get_by_id(session, tenant_id, page_id)
        if page is None:
            return False
        await session.delete(page)
        await session.flush()
        return True


cms_page_repo = CmsPageRepository()
