# Owner A — backend/app/models/chunk.py
#
# Chunks are fixed-size text windows cut from CMS pages, each paired with a
# BGE-small-en-v1.5 embedding (768 dimensions). ANN search over this table
# is how RAG retrieval works.
#
# The IVFFlat index and the tenant_id index are created in the Alembic migration —
# SQLAlchemy's Index() cannot express IVFFlat, so raw SQL is used there.

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Chunk(Base, TenantMixin, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # FK to the source CMS page — CASCADE so deleting a page removes its chunks
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cms_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Position of this chunk within the page (0-based) — used for result ordering
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)

    # 768-dim BGE-small-en-v1.5 vector. NULL until embedding pipeline runs.
    # ANN queries filter to WHERE tenant_id = :tid before cosine distance ranking.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    # Optional metadata: source URL, section heading, etc. — used by reranker
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
