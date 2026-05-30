# Owner B — backend/app/services/router.py
#
# Classifier-driven hybrid router. Routes each turn to the cheapest workflow
# that can handle it correctly.
#
# faq  ≥ 0.80  → RAG workflow: 1 embed + 1 LLM call, no tool loop
# lead ≥ 0.80  → direct lead: 1 LLM call → capture_lead tool
# escalate ≥ 0.80 → direct escalate: 1 LLM call → escalate tool
# anything else  → full bounded agent loop (most expensive)
#
# Emits a router_decision structured log event on every turn so efficiency
# metrics (% turns off agent) can be computed from logs (B-034/B-035).

import uuid

import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_config import AgentConfig
from app.services.agent import run_agent
from app.services.classifier_client import ClassifyResult
from app.services.cost_meter import record_llm_usage
from app.services.embeddings_client import EmbeddingsClient
from app.services.llm_client import LLMClient
from app.services.rag import retrieve

log = structlog.get_logger()

# Confidence threshold below which any intent is treated as ambiguous (per INTERFACES.md)
_CONFIDENCE_THRESHOLD = 0.80

# ── Prompt fragments used by direct (non-agent) workflows ────────────────────

_LEAD_SYSTEM = """\
{persona_name} is capturing a visitor's contact details.

The visitor has expressed clear purchase or contact intent. Call the capture_lead tool \
immediately using the name and contact information present in the visitor's message. \
If the message lacks a name or contact, ask for the missing piece in one short sentence.
"""

_ESCALATE_SYSTEM = """\
{persona_name} is escalating this conversation to a human agent.

The visitor needs human assistance. Call the escalate tool with a concise reason \
summarising why the visitor needs a human. Use the conversation_id provided.
"""

_FAQ_SYSTEM = """\
You are {persona_name}, a helpful assistant.
{persona_description}

Answer the visitor's question using ONLY the context below. \
If the answer is not in the context, say you don't have that specific information \
and offer to connect them with the team. Do not fabricate facts.

--- Context ---
{context}
"""

# Inline tool schemas for single-shot direct workflows (no iteration needed)
_CAPTURE_LEAD_TOOL = {
    "name": "capture_lead",
    "description": "Record the visitor's contact information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name":    {"type": "string", "description": "Visitor name, max 255 characters"},
            "contact": {"type": "string", "description": "Email or E.164 phone, max 255 chars"},
            "intent":  {"type": "string", "description": "What the visitor wants, max 1000 chars"},
        },
        "required": ["name", "contact", "intent"],
    },
}

_ESCALATE_TOOL = {
    "name": "escalate",
    "description": "Hand the conversation to a human agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why escalation is needed, max 500 chars"},
            "conversation_id": {"type": "string", "description": "The session UUID"},
        },
        "required": ["reason", "conversation_id"],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _history_to_messages(history: list[dict]) -> list[dict]:
    return [{"role": h["role"], "content": h["content"]} for h in history]


# ── Direct workflow: FAQ (embed → ANN → LLM answer, no tool loop) ────────────

async def _faq_workflow(
    message: str,
    history: list[dict],
    agent_config: AgentConfig,
    tenant_id: uuid.UUID,
    session: AsyncSession,
    llm_client: LLMClient,
    embeddings_client: EmbeddingsClient,
) -> str:
    chunks = await retrieve(message, tenant_id, session, embeddings_client)

    if chunks:
        context = "\n\n---\n\n".join(c["content"] for c in chunks)
    else:
        context = "No relevant information found in the knowledge base."

    system = _FAQ_SYSTEM.format(
        persona_name=agent_config.persona_name,
        persona_description=agent_config.persona_description or "",
        context=context,
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(_history_to_messages(history))
    messages.append({"role": "user", "content": message})

    response = await llm_client.complete(messages=messages, max_tokens=1024, tenant_id=tenant_id)
    await record_llm_usage(
        session, tenant_id, response.usage.input_tokens, response.usage.output_tokens
    )
    return response.content


# ── Direct workflow: lead (single LLM call → capture_lead tool) ───────────────

async def _lead_workflow(
    message: str,
    history: list[dict],
    agent_config: AgentConfig,
    tenant_id: uuid.UUID,
    session_id: str,
    session: AsyncSession,
    redis: aioredis.Redis,
    llm_client: LLMClient,
) -> str:
    from app.tools.capture_lead import capture_lead

    try:
        system = _LEAD_SYSTEM.format(persona_name=agent_config.persona_name)
        messages = [{"role": "system", "content": system}]
        messages.extend(_history_to_messages(history))
        messages.append({"role": "user", "content": message})

        # Force the model to call capture_lead — without this, Claude often chooses
        # to reply with text ("thanks, we'll get back to you") and never invokes the
        # tool, so no row lands in the leads table.
        response = await llm_client.complete(
            messages=messages,
            tools=[_CAPTURE_LEAD_TOOL],
            max_tokens=512,
            tenant_id=tenant_id,
            tool_choice={"type": "tool", "name": "capture_lead"},
        )
        await record_llm_usage(
            session, tenant_id, response.usage.input_tokens, response.usage.output_tokens
        )

        if (
            response.stop_reason == "tool_use"
            and response.tool_use
            and response.tool_use["name"] == "capture_lead"
        ):
            inp = response.tool_use["input"]
            result = await capture_lead(
                name=inp.get("name", ""),
                contact=inp.get("contact", ""),
                intent=inp.get("intent", message[:1000]),
                tenant_id=tenant_id,
                session_id=session_id,
                session=session,
                redis=redis,
                classifier_score=classify_result.confidence,
            )
            if result.get("captured"):
                return "Thank you! I've noted your details and our team will be in touch shortly."
            return result.get(
                "reason", "I wasn't able to capture your details right now. Please try again."
            )

        # LLM chose to ask for more info rather than call the tool
        fallback = "I'd love to connect you with our team. Could you share your contact info?"
        return response.content or fallback

    except Exception as exc:
        log.error("lead_workflow_error", tenant_id=str(tenant_id), error=str(exc))
        return "Thank you for reaching out! Our team will follow up with you shortly."


# ── Direct workflow: escalate (single LLM call → escalate tool) ──────────────

async def _escalate_workflow(
    message: str,
    history: list[dict],
    agent_config: AgentConfig,
    tenant_id: uuid.UUID,
    session_id: str,
    session: AsyncSession,
    llm_client: LLMClient,
) -> str:
    from app.tools.escalate import escalate

    system = _ESCALATE_SYSTEM.format(persona_name=agent_config.persona_name)
    messages = [{"role": "system", "content": system}]
    messages.extend(_history_to_messages(history))
    messages.append({"role": "user", "content": message})

    # Force the escalate tool call for the same reason as capture_lead above.
    response = await llm_client.complete(
        messages=messages,
        tools=[_ESCALATE_TOOL],
        max_tokens=256,
        tenant_id=tenant_id,
        tool_choice={"type": "tool", "name": "escalate"},
    )
    await record_llm_usage(
        session, tenant_id, response.usage.input_tokens, response.usage.output_tokens
    )

    if (
        response.stop_reason == "tool_use"
        and response.tool_use
        and response.tool_use["name"] == "escalate"
    ):
        inp = response.tool_use["input"]
        await escalate(
            reason=inp.get("reason", message[:500]),
            conversation_id=inp.get("conversation_id", session_id),
            tenant_id=tenant_id,
            session=session,
        )
        return "I've connected you with our support team. A human agent will be with you shortly."

    fallback = "I'm escalating this to our team. Someone will reach out to you shortly."
    return response.content or fallback


# ── Main router ───────────────────────────────────────────────────────────────

async def route(
    message: str,
    classify_result: ClassifyResult,
    tenant_id: uuid.UUID,
    session_id: str,
    history: list[dict],
    session: AsyncSession,
    redis: aioredis.Redis,
    llm_client: LLMClient,
    embeddings_client: EmbeddingsClient,
    agent_config: AgentConfig,
    system_prompt: str,
) -> str:
    """Route a classified message to the cheapest appropriate workflow.

    Routing table (per INTERFACES.md):
      spam           → already handled upstream; never reaches here
      faq  ≥ 0.80   → RAG workflow (embed + LLM, no tool loop)
      lead ≥ 0.80   → direct lead workflow (1 LLM call + capture_lead)
      escalate ≥ 0.80 → direct escalate workflow (1 LLM call + escalate)
      anything else  → full agent (bounded tool loop)

    Confidence < 0.80 always falls through to the agent regardless of label.
    """
    intent = classify_result.intent
    confidence = classify_result.confidence
    high_confidence = confidence >= _CONFIDENCE_THRESHOLD

    # B-034 structured log — every turn recorded for efficiency metrics
    routed_to = "agent"
    if intent == "faq" and high_confidence:
        routed_to = "workflow:faq"
    elif intent == "lead" and high_confidence:
        routed_to = "workflow:lead"
    elif intent == "escalate" and high_confidence:
        routed_to = "workflow:escalate"

    log.info(
        "router_decision",
        tenant_id=str(tenant_id),
        intent=intent,
        confidence=round(confidence, 4),
        routed_to=routed_to,
    )

    if intent == "faq" and high_confidence:
        return await _faq_workflow(
            message, history, agent_config, tenant_id, session, llm_client, embeddings_client
        )

    if intent == "lead" and high_confidence:
        return await _lead_workflow(
            message, history, agent_config, tenant_id, session_id, session, redis, llm_client
        )

    if intent == "escalate" and high_confidence:
        return await _escalate_workflow(
            message, history, agent_config, tenant_id, session_id, session, llm_client
        )

    # ambiguous, low-confidence, or unknown intent → full agent
    return await run_agent(
        message=message,
        tenant_id=tenant_id,
        session_id=session_id,
        history=history,
        session=session,
        redis=redis,
        llm_client=llm_client,
        embeddings_client=embeddings_client,
        agent_config=agent_config,
        system_prompt=system_prompt,
        classifier_score=classify_result.confidence,
    )
