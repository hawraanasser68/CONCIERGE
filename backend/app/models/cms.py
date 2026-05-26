# Owner A — backend/app/models/cms.py
#
# CMS pages — tenant-authored content that feeds the RAG knowledge base.
# Owner B writes the CMS routes (crud + publish toggle) and the embedding pipeline
# that chunks published pages and stores vectors in the chunks table.

import uuid

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class CmsPage(Base, TenantMixin, TimestampMixin):
    __tablename__ = "cms_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)

    # slug is the URL-friendly identifier e.g. "pricing-faq"
    # Unique per tenant — two tenants can have the same slug without conflict
    slug: Mapped[str] = mapped_column(String, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Only published pages are indexed into chunks for RAG retrieval.
    # Toggling is_published to False removes the page from future RAG results
    # (existing chunks are deleted by the re-indexing background task).
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        # Same slug is fine across tenants, but not within one tenant
        UniqueConstraint("tenant_id", "slug", name="cms_pages_tenant_slug_key"),
    )
