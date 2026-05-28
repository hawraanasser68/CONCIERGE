# Owner B — backend/app/routes/chat.py
#
# POST /api/v1/chat/message — main chat endpoint consumed by the widget.
# Auth: widget JWT validated by get_widget_session (signature, expiry, origin allowlist).
#
# Request flow (8 steps):
#   1. Guardrails input check  (fail closed → 503 / 400)
#   2. Rate limit              (60 / hour per session → 429)
#   3. Classify                (fail open → ambiguous on error)
#   4. Spam drop               (generic refusal, no history written)
#   5. Load history + config
#   6. Route                   (faq / lead / escalate workflows or agent)
#   7. Guardrails output check (fail closed → 503 / safe fallback)
#   8. Persist turn + increment counter

import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_redis, get_session, get_widget_session
from app.models.agent_config import AgentConfig
from app.models.tenant import Tenant
from app.repositories.agent_config_repo import agent_config_repo
from app.services.classifier_client import ClassifierClient, get_classifier_client
from app.services.cost_meter import record_classify_call
from app.services.embeddings_client import EmbeddingsClient, get_embeddings_client
from app.services.guardrails_client import (
    GuardrailsClient,
    GuardrailsUnavailableError,
    get_guardrails_client,
)
from app.services.llm_client import LLMClient, get_llm_client
from app.services.rate_limiter import check_rate_limit, increment_rate_limit
from app.services.router import route
from app.services.session_memory import append_message, get_history

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

_SPAM_REFUSAL = "I'm sorry, I'm not able to help with that request."
_OUTPUT_BLOCKED = "I'm sorry, I'm not able to provide that response. Please contact us directly."
_ROUTING_ERROR = "I'm sorry, I encountered an issue processing your request. Please try again."


def _load_system_prompt(agent_config: AgentConfig, tenant_name: str) -> str:
    """Read the agent system prompt template and fill in per-tenant variables."""
    try:
        with open("/app/prompts/system_agent.md") as f:
            template = f.read()
        return template.format(
            persona_name=agent_config.persona_name,
            persona_description=agent_config.persona_description or "",
            tenant_name=tenant_name,
        )
    except Exception:
        return (
            f"You are {agent_config.persona_name}, a helpful AI assistant for "
            f"{tenant_name}. Be concise and professional."
        )


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
    db: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
    guardrails: GuardrailsClient = Depends(get_guardrails_client),
    classifier: ClassifierClient = Depends(get_classifier_client),
    llm: LLMClient = Depends(get_llm_client),
    embeddings: EmbeddingsClient = Depends(get_embeddings_client),
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

    # ── 2. Rate limit ─────────────────────────────────────────────────────────
    if not await check_rate_limit(redis, tenant_id, "chat", session_id=session_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # ── 3. Classify (fail open — classifier_client returns ambiguous on 5xx) ──
    classify_result = await classifier.classify(guard.redacted_message, tenant_id)
    await record_classify_call(db, tenant_id)

    # Spam: generic refusal, do NOT persist message content
    if classify_result.intent == "spam":
        await increment_rate_limit(redis, tenant_id, "chat", session_id=session_id)
        return MessageResponse(response=_SPAM_REFUSAL, session_id=session_id)

    # ── 4. Load history and agent config ──────────────────────────────────────
    history = await get_history(redis, tenant_id, session_id)

    config = await agent_config_repo.get_for_tenant(db, tenant_id)
    if config is None:
        config = AgentConfig(tenant_id=tenant_id)  # in-memory defaults; no DB write

    tenant_row = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    tenant_name = tenant_row.name if tenant_row else "this business"
    system_prompt = _load_system_prompt(config, tenant_name)

    # ── 5. Persist user turn (redacted — PII stripped by guardrails) ──────────
    await append_message(
        redis, tenant_id, session_id,
        role="user", content=guard.redacted_message,
    )

    # ── 6. Route → workflow or agent ──────────────────────────────────────────
    try:
        response_text = await route(
            message=guard.redacted_message,
            classify_result=classify_result,
            tenant_id=tenant_id,
            session_id=session_id,
            history=history,
            session=db,
            redis=redis,
            llm_client=llm,
            embeddings_client=embeddings,
            agent_config=config,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        log.error("routing_error", tenant_id=str(tenant_id), session_id=session_id, error=str(exc))
        response_text = _ROUTING_ERROR

    # ── 7. Guardrails output check (fail closed) ───────────────────────────────
    try:
        out_guard = await guardrails.check_output(response_text, tenant_id, session_id)
        if not out_guard.allowed:
            response_text = _OUTPUT_BLOCKED
        else:
            response_text = out_guard.redacted_message
    except GuardrailsUnavailableError:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # ── 8. Persist assistant turn + increment counter ─────────────────────────
    await append_message(
        redis, tenant_id, session_id,
        role="assistant", content=response_text,
    )
    await increment_rate_limit(redis, tenant_id, "chat", session_id=session_id)

    return MessageResponse(response=response_text, session_id=session_id)
