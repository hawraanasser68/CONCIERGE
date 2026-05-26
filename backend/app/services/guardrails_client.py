# Owner B
import uuid
from dataclasses import dataclass, field

import structlog
from fastapi import Request
from httpx import AsyncClient

log = structlog.get_logger()

_GUARDRAILS_URL = "http://guardrails:8002"


class GuardrailsUnavailableError(Exception):
    """Raised when the guardrails sidecar is unreachable or returns 5xx.

    Callers must treat this as blocked — never allow a message through on sidecar failure.
    """


@dataclass
class GuardrailResult:
    allowed: bool
    redacted_message: str
    flagged_categories: list[str] = field(default_factory=list)
    block_reason: str | None = None


class GuardrailsClient:
    def __init__(self, http_client: AsyncClient, token: str) -> None:
        self._http = http_client
        self._token = token

    async def check_input(
        self, message: str, tenant_id: uuid.UUID, session_id: str
    ) -> GuardrailResult:
        return await self._check(message, tenant_id, session_id, direction="input", path="/check/input")

    async def check_output(
        self, message: str, tenant_id: uuid.UUID, session_id: str
    ) -> GuardrailResult:
        return await self._check(message, tenant_id, session_id, direction="output", path="/check/output")

    async def _check(
        self,
        message: str,
        tenant_id: uuid.UUID,
        session_id: str,
        direction: str,
        path: str,
    ) -> GuardrailResult:
        try:
            response = await self._http.post(
                f"{_GUARDRAILS_URL}{path}",
                json={
                    "message": message,
                    "tenant_id": str(tenant_id),
                    "session_id": session_id,
                    "direction": direction,
                },
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            data = response.json()
            return GuardrailResult(
                allowed=data["allowed"],
                redacted_message=data["redacted_message"],
                flagged_categories=data.get("flagged_categories", []),
                block_reason=data.get("block_reason"),
            )
        except Exception as exc:
            # Fail CLOSED: a sidecar failure is a security failure.
            # Never allow a message through because the sidecar is unreachable.
            log.error("guardrails_unavailable", direction=direction, error=str(exc))
            raise GuardrailsUnavailableError(
                f"Guardrails sidecar unreachable ({direction}): {exc}"
            ) from exc


def get_guardrails_client(request: Request) -> GuardrailsClient:
    return GuardrailsClient(
        http_client=request.app.state.http_client,
        token=request.app.state.guardrails_token,
    )
