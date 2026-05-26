# Owner B
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_tenant_id, get_session
from app.repositories.cms_page_repo import cms_page_repo

router = APIRouter(prefix="/api/v1/cms", tags=["cms"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CreatePageRequest(BaseModel):
    title: str
    slug: str
    content: str
    is_published: bool = False


class UpdatePageRequest(BaseModel):
    title: str | None = None
    slug: str | None = None
    content: str | None = None
    is_published: bool | None = None


class PageResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    slug: str
    content: str
    is_published: bool


# ── Routes ────────────────────────────────────────────────────────────────────

def _require_tenant(tenant_id: uuid.UUID | None) -> uuid.UUID:
    """Guard: tenant_manager role (tenant_id=None) cannot access CMS routes."""
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


@router.post("/pages", response_model=PageResponse, status_code=201)
async def create_page(
    body: CreatePageRequest,
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> PageResponse:
    tid = _require_tenant(tenant_id)
    try:
        page = await cms_page_repo.create(
            session, tid,
            title=body.title,
            slug=body.slug,
            content=body.content,
            is_published=body.is_published,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A page with this slug already exists for this tenant")

    return PageResponse(
        id=page.id,
        tenant_id=page.tenant_id,
        title=page.title,
        slug=page.slug,
        content=page.content,
        is_published=page.is_published,
    )


@router.get("/pages", response_model=list[PageResponse])
async def list_pages(
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> list[PageResponse]:
    tid = _require_tenant(tenant_id)
    pages = await cms_page_repo.list_all(session, tid)
    return [
        PageResponse(
            id=p.id,
            tenant_id=p.tenant_id,
            title=p.title,
            slug=p.slug,
            content=p.content,
            is_published=p.is_published,
        )
        for p in pages
    ]


@router.get("/pages/{page_id}", response_model=PageResponse)
async def get_page(
    page_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> PageResponse:
    tid = _require_tenant(tenant_id)
    page = await cms_page_repo.get_by_id(session, tid, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(
        id=page.id,
        tenant_id=page.tenant_id,
        title=page.title,
        slug=page.slug,
        content=page.content,
        is_published=page.is_published,
    )


@router.put("/pages/{page_id}", response_model=PageResponse)
async def update_page(
    page_id: uuid.UUID,
    body: UpdatePageRequest,
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> PageResponse:
    tid = _require_tenant(tenant_id)
    try:
        page = await cms_page_repo.update(
            session, tid, page_id,
            title=body.title,
            slug=body.slug,
            content=body.content,
            is_published=body.is_published,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A page with this slug already exists for this tenant")
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageResponse(
        id=page.id,
        tenant_id=page.tenant_id,
        title=page.title,
        slug=page.slug,
        content=page.content,
        is_published=page.is_published,
    )


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(
    page_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> None:
    tid = _require_tenant(tenant_id)
    deleted = await cms_page_repo.delete(session, tid, page_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")
    await session.commit()
