# Owner B — backend/app/tools/rag_search.py
#
# The rag_search agent tool. Enforces the 500-char query cap from the LLM-facing
# schema, delegates to rag.retrieve() for embed → ANN → diversity rerank → top-5,
# and records embed token usage for per-tenant cost attribution.
#
# tenant_id is injected server-side by agent._dispatch() — it is absent from the
# LLM-facing input schema so prompt injection cannot override tenant context.

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings_client import EmbeddingsClient
from app.services.rag import retrieve
from app.services.cost_meter import record_embed_usage


async def rag_search(
    query: str,
    tenant_id: uuid.UUID,           # injected from get_current_tenant_id — never from LLM args
    session: AsyncSession,
    embeddings_client: EmbeddingsClient,
) -> dict:
    """RAG retrieval tool: embed → tenant-scoped ANN → diversity rerank → top-5.

    Returns the INTERFACES.md shape: {chunks: [...], retrieved_count: N}.
    Embed token cost is recorded here so the caller (agent dispatch) doesn't need to.
    """
    query = query[:500]  # enforce LLM-facing schema max length

    chunks = await retrieve(query, tenant_id, session, embeddings_client)

    # Approximate embed token count for cost attribution (~4 chars/token)
    await record_embed_usage(session, tenant_id, len(query) // 4 or 1)

    return {
        "chunks": chunks,
        "retrieved_count": len(chunks),
    }
