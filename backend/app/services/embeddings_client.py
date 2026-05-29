# Owner B — backend/app/services/embeddings_client.py
#
# HTTP client for POST /embed on the model server (BGE-small ONNX, Owner C).
# Used by the RAG retrieval path (single embed per query) and the indexing
# pipeline (batch via concurrent single calls — the modelserver has no batch
# endpoint; see INTERFACES.md §2 which defines only POST /embed).
# Errors propagate to the caller — no fail-open/closed policy at this layer.
#
# Usage:
#   client = get_embeddings_client(request)
#   vector = await client.embed(text)           # single
#   vectors = await client.embed_batch(texts)   # concurrent single calls

import asyncio
from dataclasses import dataclass

import structlog
from fastapi import Request
from httpx import AsyncClient

log = structlog.get_logger()

_MODELSERVER_URL = "http://modelserver:8001"


@dataclass
class EmbedResult:
    embedding: list[float]
    token_count: int


class EmbeddingsClient:
    def __init__(self, http_client: AsyncClient, token: str) -> None:
        self._http = http_client
        self._token = token

    async def embed(self, text: str) -> list[float]:
        response = await self._http.post(
            f"{_MODELSERVER_URL}/embed",
            json={"text": text},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    async def embed_batch(
        self, texts: list[str], *, max_concurrency: int = 5
    ) -> list[list[float]]:
        """Embed multiple texts concurrently (one POST /embed per text).

        Preserves input order. The modelserver exposes only POST /embed —
        there is no batch endpoint (see INTERFACES.md).

        Concurrency is capped (default 5) because the modelserver runs a
        single uvicorn worker; firing 20+ requests in parallel made the
        later ones queue past backend's shared httpx 10s timeout and abort
        the entire index_page task with httpcore.PoolTimeout, leaving the
        chunks table empty.
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _one(text: str) -> list[float]:
            async with sem:
                return await self.embed(text)

        return list(await asyncio.gather(*(_one(t) for t in texts)))


def get_embeddings_client(request: Request) -> EmbeddingsClient:
    return EmbeddingsClient(
        http_client=request.app.state.http_client,
        token=request.app.state.modelserver_token,
    )
