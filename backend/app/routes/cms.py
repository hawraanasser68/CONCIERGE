# Owner B — backend/app/routes/cms.py
#
# CMS page management at /api/v1/cms. Tenant-authored content that feeds the RAG
# knowledge base. All 6 endpoints: pages CRUD + publish toggle.
# Auth: platform user JWT via get_current_tenant_id (not widget tokens).
#
# Background indexing: create/update/publish routes schedule index_page() as a
# FastAPI BackgroundTask so the response returns immediately while chunks are rebuilt.
# On unpublish or delete, stale chunks are removed in a background delete task.
# Background tasks open their own DB session (request session is closed by then).

import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_tenant_id, get_session
from app.repositories.chunk_repo import chunk_repo
from app.repositories.cms_page_repo import cms_page_repo
from app.services.embeddings_client import EmbeddingsClient
from app.services.rag import index_page
from app.tenancy.rls import set_tenant_rls

log = structlog.get_logger()

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


# ── Background task helpers ───────────────────────────────────────────────────

async def _index_page_bg(
    session_factory,
    http_client,
    modelserver_token: str,
    page_id: uuid.UUID,
    tenant_id: uuid.UUID,
    title: str,
    content: str,
) -> None:
    """Re-chunk, embed, and replace chunks for a page. Runs after response is sent."""
    embeddings_client = EmbeddingsClient(
        http_client=http_client, token=modelserver_token
    )
    async with session_factory() as session:
        await set_tenant_rls(session, tenant_id)
        n = await index_page(
            page_id, tenant_id, title, content,
            source_url=None, session=session,
            embeddings_client=embeddings_client,
        )
        await session.commit()
    log.info("background_index_complete", page_id=str(page_id), chunks=n)


async def _delete_chunks_bg(
    session_factory,
    tenant_id: uuid.UUID,
    page_id: uuid.UUID,
) -> None:
    """Remove all chunks for a page (on unpublish or delete). Runs after response."""
    async with session_factory() as session:
        await set_tenant_rls(session, tenant_id)
        await chunk_repo.delete_for_page(session, tenant_id, page_id)
        await session.commit()
    log.info("background_chunks_deleted", page_id=str(page_id))


def _schedule_index(
    background_tasks: BackgroundTasks,
    request: Request,
    page_id: uuid.UUID,
    tenant_id: uuid.UUID,
    title: str,
    content: str,
) -> None:
    background_tasks.add_task(
        _index_page_bg,
        request.app.state.session_factory,
        request.app.state.http_client,
        request.app.state.modelserver_token,
        page_id, tenant_id, title, content,
    )


def _schedule_delete_chunks(
    background_tasks: BackgroundTasks,
    request: Request,
    tenant_id: uuid.UUID,
    page_id: uuid.UUID,
) -> None:
    background_tasks.add_task(
        _delete_chunks_bg,
        request.app.state.session_factory,
        tenant_id, page_id,
    )


# ── Guards ────────────────────────────────────────────────────────────────────

def _require_tenant(tenant_id: uuid.UUID | None) -> uuid.UUID:
    """Reject tenant_manager role — they have no tenant context for CMS operations."""
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tenant_id


def _to_response(page) -> PageResponse:
    return PageResponse(
        id=page.id,
        tenant_id=page.tenant_id,
        title=page.title,
        slug=page.slug,
        content=page.content,
        is_published=page.is_published,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/pages", response_model=PageResponse, status_code=201)
async def create_page(
    body: CreatePageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
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
        raise HTTPException(
            status_code=409,
            detail="A page with this slug already exists for this tenant",
        )

    if page.is_published:
        _schedule_index(background_tasks, request, page.id, tid, page.title, page.content)

    return _to_response(page)


@router.get("/pages", response_model=list[PageResponse])
async def list_pages(
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> list[PageResponse]:
    tid = _require_tenant(tenant_id)
    pages = await cms_page_repo.list_all(session, tid)
    return [_to_response(p) for p in pages]


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
    return _to_response(page)


@router.put("/pages/{page_id}", response_model=PageResponse)
async def update_page(
    page_id: uuid.UUID,
    body: UpdatePageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
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
        raise HTTPException(
            status_code=409,
            detail="A page with this slug already exists for this tenant",
        )
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    if page.is_published:
        _schedule_index(background_tasks, request, page.id, tid, page.title, page.content)
    else:
        _schedule_delete_chunks(background_tasks, request, tid, page.id)

    return _to_response(page)


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(
    page_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> None:
    tid = _require_tenant(tenant_id)
    deleted = await cms_page_repo.delete(session, tid, page_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")
    await session.commit()
    _schedule_delete_chunks(background_tasks, request, tid, page_id)


@router.post("/pages/{page_id}/publish", response_model=PageResponse)
async def toggle_publish(
    page_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    tenant_id: uuid.UUID | None = Depends(get_current_tenant_id),
) -> PageResponse:
    """Toggle is_published. Publishing triggers background re-indexing;
    unpublishing schedules chunk deletion so stale vectors are removed."""
    tid = _require_tenant(tenant_id)
    page = await cms_page_repo.get_by_id(session, tid, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    page = await cms_page_repo.update(
        session, tid, page_id, is_published=not page.is_published
    )
    await session.commit()

    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    if page.is_published:
        _schedule_index(background_tasks, request, page.id, tid, page.title, page.content)
    else:
        _schedule_delete_chunks(background_tasks, request, tid, page.id)

    return _to_response(page)
