# Owner B
import uuid
from dataclasses import dataclass

import structlog
from fastapi import Request
from httpx import AsyncClient

log = structlog.get_logger()

_MODELSERVER_URL = "http://modelserver:8001"


@dataclass
class ClassifyResult:
    intent: str
    confidence: float


class ClassifierClient:
    def __init__(self, http_client: AsyncClient, token: str) -> None:
        self._http = http_client
        self._token = token

    async def classify(self, text: str, tenant_id: uuid.UUID) -> ClassifyResult:
        try:
            response = await self._http.post(
                f"{_MODELSERVER_URL}/classify",
                json={"text": text, "tenant_id": str(tenant_id)},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            data = response.json()
            return ClassifyResult(intent=data["intent"], confidence=data["confidence"])
        except Exception as exc:
            # Fail open: classifier unavailable → treat as ambiguous so the agent handles it.
            # Visitor still gets a response; a downed classifier is a degraded experience, not a
            # security failure.
            log.warning("classifier_unavailable", error=str(exc))
            return ClassifyResult(intent="ambiguous", confidence=0.0)


def get_classifier_client(request: Request) -> ClassifierClient:
    return ClassifierClient(
        http_client=request.app.state.http_client,
        token=request.app.state.modelserver_token,
    )
