# Owner B — backend/app/services/rag.py
#
# RAG pipeline: text chunking, ANN retrieval, and page re-indexing.
#
# split_into_chunks() — sentence-window chunker: ~512-token window (2048 chars),
#   ~50-token overlap (200 chars), breaks at sentence boundaries where possible.
#
# retrieve() — embeds a query, runs a tenant-scoped pgvector ANN search (pool of 20),
#   then applies per-page diversity reranking (max 2 chunks per source page) before
#   returning the top-5 results. Called by the rag_search tool and the FAQ workflow.
#
# index_page() — deletes stale chunks for a page, re-chunks the content, batch-embeds
#   in groups of 100, and bulk-inserts new Chunk rows. Called by CMS routes on publish.

import uuid
from collections import defaultdict

import structlog

from app.models.chunk import Chunk
from app.repositories.chunk_repo import chunk_repo
from app.services.embeddings_client import EmbeddingsClient
from app.services.cost_meter import record_embed_usage

log = structlog.get_logger()

# Chunking parameters (512-token window, 50-token overlap; ~4 chars/token)
_CHUNK_CHARS = 2048
_OVERLAP_CHARS = 200
# Retrieval settings
_ANN_POOL = 20       # fetch top-N before rerank
_TOP_N = 5           # final results returned to callers
_MAX_PER_PAGE = 2    # diversity cap: no more than 2 chunks from the same source page


# ── Chunking ─────────────────────────────────────────────────────────────────

def split_into_chunks(text: str) -> list[str]:
    """Sentence-window chunker: 512-token window (~2048 chars), 50-token overlap (~200 chars).

    Prefers sentence boundaries so chunks end at a period where possible.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_CHARS
        if end < len(text):
            # Try to break at the last sentence boundary within the window
            break_point = text.rfind(". ", start + _CHUNK_CHARS // 2, end)
            if break_point == -1:
                break_point = end
            else:
                break_point += 2  # include ". "
        else:
            break_point = len(text)
        chunk = text[start:break_point].strip()
        if chunk:
            chunks.append(chunk)
        start = max(start + 1, break_point - _OVERLAP_CHARS)
    return chunks


# ── Reranking ─────────────────────────────────────────────────────────────────

def rerank(rows: list[tuple[Chunk, float]], top_n: int = _TOP_N) -> list[tuple[Chunk, float]]:
    """Per-page diversity rerank: cap at _MAX_PER_PAGE chunks per source page, return top_n.

    Justification: naive ANN may return 5 chunks from one dense FAQ page, starving
    the result set of breadth. This rerank ensures coverage across topics. Chunks are
    still ordered by ANN cosine distance within the diversity constraint, so retrieval
    precision is preserved while recall breadth improves.
    """
    seen_per_page: dict[uuid.UUID, int] = defaultdict(int)
    diverse: list[tuple[Chunk, float]] = []
    for chunk, distance in rows:
        if seen_per_page[chunk.page_id] < _MAX_PER_PAGE:
            diverse.append((chunk, distance))
            seen_per_page[chunk.page_id] += 1
        if len(diverse) == top_n:
            break
    return diverse


# ── Retrieval (used by rag_search tool and FAQ workflow) ─────────────────────

async def retrieve(
    query: str,
    tenant_id: uuid.UUID,
    session,                        # AsyncSession — untyped to avoid circular import
    embeddings_client: EmbeddingsClient,
) -> list[dict]:
    """Embed query → ANN pool → diversity rerank → top-5 chunks.

    Returns list of {content, source_url, score} dicts matching the INTERFACES.md shape.
    score = 1 - cosine_distance (higher is better).
    """
    query_embedding = await embeddings_client.embed(query)

    rows = await chunk_repo.ann_search(
        session, tenant_id, query_embedding, top_k=_ANN_POOL
    )
    ranked = rerank(rows, top_n=_TOP_N)

    return [
        {
            "content": chunk.chunk_text,
            "source_url": (chunk.metadata_ or {}).get("source_url"),
            "score": round(1.0 - distance, 4),
        }
        for chunk, distance in ranked
    ]


# ── Indexing pipeline (used by CMS routes on publish, B-021) ─────────────────

async def index_page(
    page_id: uuid.UUID,
    tenant_id: uuid.UUID,
    title: str,
    content: str,
    source_url: str | None,
    session,                        # AsyncSession
    embeddings_client: EmbeddingsClient,
) -> int:
    """Delete old chunks for a page, re-chunk, embed in batches of 100, insert.

    Returns the number of chunks inserted.
    """
    await chunk_repo.delete_for_page(session, tenant_id, page_id)

    texts = split_into_chunks(f"{title}\n\n{content}")
    if not texts:
        return 0

    # Batch embed in groups of 100 to stay within modelserver limits
    all_embeddings: list[list[float]] = []
    batch_size = 100
    total_tokens = 0
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embeddings = await embeddings_client.embed_batch(batch)
        all_embeddings.extend(embeddings)
        # Approximate token count for cost attribution (~4 chars/token per batch)
        total_tokens += sum(len(t) // 4 for t in batch)

    await record_embed_usage(session, tenant_id, total_tokens)

    chunks = [
        Chunk(
            tenant_id=tenant_id,
            page_id=page_id,
            chunk_index=idx,
            chunk_text=text,
            embedding=embedding,
            metadata_={"source_url": source_url} if source_url else None,
        )
        for idx, (text, embedding) in enumerate(zip(texts, all_embeddings))
    ]
    await chunk_repo.bulk_insert(session, chunks)
    log.info("page_indexed", page_id=str(page_id), chunks=len(chunks))
    return len(chunks)
