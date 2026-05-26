# Owner B
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import get_redis, get_widget_session
from app.services.classifier_client import ClassifierClient, get_classifier_client
from app.services.guardrails_client import GuardrailsClient, GuardrailsUnavailableError, get_guardrails_client
from app.services.rate_limiter import check_rate_limit, increment_rate_limit
from app.services.session_memory import append_message

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

_SPAM_REFUSAL = "I'm sorry, I'm not able to help with that request."
_PLACEHOLDER = "Thank you for your message. I'll be with you shortly."


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    response: str
    session_id: str


@router.post("/message", response_model=MessageResponse)
async def send_message(
    body: MessageRequest,
    request: Request,
    session_data: dict = Depends(get_widget_session),
    redis: aioredis.Redis = Depends(get_redis),
    guardrails: GuardrailsClient = Depends(get_guardrails_client),
    classifier: ClassifierClient = Depends(get_classifier_client),
) -> MessageResponse:
    tenant_id = uuid.UUID(session_data["tenant_id"])
    session_id: str = session_data["session_id"]

    # ── 1. Guardrails input check (fail closed) ───────────────────────────────
    try:
        guard = await guardrails.check_input(body.message, tenant_id, session_id)
    except GuardrailsUnavailableError:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    if not guard.allowed:
        raise HTTPException(
            status_code=400,
            detail=guard.block_reason or "Message not allowed",
        )

    # ── 2. Rate limit (checked before classify to avoid wasteful calls) ───────
    if not await check_rate_limit(redis, tenant_id, "chat", session_id=session_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # ── 3. Classify the redacted message ─────────────────────────────────────
    classify_result = await classifier.classify(guard.redacted_message, tenant_id)

    # Spam: return generic refusal and do NOT log the content
    if classify_result.intent == "spam":
        await increment_rate_limit(redis, tenant_id, "chat", session_id=session_id)
        return MessageResponse(response=_SPAM_REFUSAL, session_id=session_id)

    # ── 4. Persist user turn (redacted content — PII already stripped) ────────
    await append_message(
        redis, tenant_id, session_id,
        role="user", content=guard.redacted_message,
    )

    # ── 5. Placeholder — router/agent wired in B-009/B-019 ───────────────────
    await increment_rate_limit(redis, tenant_id, "chat", session_id=session_id)
    await append_message(
        redis, tenant_id, session_id,
        role="assistant", content=_PLACEHOLDER,
    )

    return MessageResponse(response=_PLACEHOLDER, session_id=session_id)
