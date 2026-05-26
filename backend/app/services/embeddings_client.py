# Owner B
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

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one request. Returns embeddings in the same order."""
        response = await self._http.post(
            f"{_MODELSERVER_URL}/embed/batch",
            json={"texts": texts},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()
        return response.json()["embeddings"]


def get_embeddings_client(request: Request) -> EmbeddingsClient:
    return EmbeddingsClient(
        http_client=request.app.state.http_client,
        token=request.app.state.modelserver_token,
    )
