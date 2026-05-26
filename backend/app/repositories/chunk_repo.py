# Owner B — backend/app/repositories/chunk_repo.py
#
# pgvector ANN search and chunk lifecycle management.
# ann_search() uses cosine distance with an explicit WHERE tenant_id = :tid (belt)
# on top of the Postgres RLS session variable (suspenders). Both must agree.
# delete_for_page() removes stale chunks before re-indexing a CMS page.
# bulk_insert() is used by the indexing pipeline after batch embedding.

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.repositories.base import TenantRepository


class ChunkRepository(TenantRepository[Chunk]):
    model = Chunk

    async def ann_search(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        embedding: list[float],
        top_k: int = 20,
    ) -> list[tuple[Chunk, float]]:
        """Cosine-distance ANN search scoped to one tenant.

        Returns (Chunk, cosine_distance) pairs, nearest first.
        Belt: explicit WHERE tenant_id = :tid. Suspenders: RLS session var set upstream.
        """
        distance_col = Chunk.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(Chunk, distance_col)
            .where(Chunk.tenant_id == tenant_id)
            .where(Chunk.embedding.is_not(None))
            .order_by(distance_col)
            .limit(top_k)
        )
        result = await session.execute(stmt)
        return [(row.Chunk, float(row.distance)) for row in result.all()]

    async def delete_for_page(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        page_id: uuid.UUID,
    ) -> int:
        """Delete all chunks for a page before re-indexing. Returns deleted row count."""
        stmt = (
            delete(Chunk)
            .where(Chunk.tenant_id == tenant_id)
            .where(Chunk.page_id == page_id)
        )
        result = await session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    async def bulk_insert(
        self,
        session: AsyncSession,
        chunks: list[Chunk],
    ) -> None:
        session.add_all(chunks)
        await session.flush()


chunk_repo = ChunkRepository()
