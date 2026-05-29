# backend/evals/rag/index_pages.py
#
# Directly indexes all published CMS pages for Tenant A (Bloom Florista).
# Bypasses the HTTP API — calls index_page() directly, same as CMS routes do.
#
# Usage:
#   docker compose exec backend sh -c "PYTHONPATH=/app python evals/rag/index_pages.py"

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.cms import CmsPage
from app.services.embeddings_client import EmbeddingsClient
from app.services.rag import index_page
from app.tenancy.rls import set_tenant_rls

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
MODELSERVER_URL = os.getenv("MODELSERVER_URL", "http://modelserver:8001")
MODELSERVER_TOKEN = os.getenv("MODELSERVER_TOKEN", "")


async def main() -> None:
    if not MODELSERVER_TOKEN:
        print("ERROR: set MODELSERVER_TOKEN env var")
        sys.exit(1)

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        embeddings_client = EmbeddingsClient(http_client=http_client, token=MODELSERVER_TOKEN)

        async with factory() as session:
            await set_tenant_rls(session, TENANT_A)
            result = await session.execute(
                select(CmsPage).where(
                    CmsPage.tenant_id == TENANT_A,
                    CmsPage.is_published == True,
                )
            )
            pages = result.scalars().all()

        print(f"Found {len(pages)} published pages to index.")

        for page in pages:
            async with factory() as session:
                await set_tenant_rls(session, TENANT_A)
                n = await index_page(
                    page.id, TENANT_A, page.title, page.content,
                    source_url=None, session=session,
                    embeddings_client=embeddings_client,
                )
                await session.commit()
            print(f"  indexed '{page.slug}' → {n} chunks")

    await engine.dispose()
    print("\nDone — all pages indexed.")


if __name__ == "__main__":
    asyncio.run(main())
