# Owner B — backend/app/services/agent.py
#
# Bounded tool-calling agent loop. Hard cap: min(config.max_tool_iterations, 10).
# An unbounded loop is a cost and DoS vector — hitting the cap returns a polite
# partial response and logs a warning.
#
# Tool dispatch injects tenant_id, session_id, session, and redis server-side.
# The LLM-facing tool schemas contain no tenant_id field — prompt injection cannot
# override tenant context regardless of what the LLM produces.
#
# Called by router.py for ambiguous / low-confidence turns.
# Direct workflows (faq, lead, escalate) bypass this loop entirely.

import json
import uuid

import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_config import AgentConfig
from app.services.cost_meter import record_llm_usage
from app.services.embeddings_client import EmbeddingsClient
from app.services.llm_client import LLMClient

log = structlog.get_logger()

_MAX_ITERATIONS_CAP = 10

# LLM-facing tool schemas (per INTERFACES.md — tenant_id absent by design)
_ALL_TOOLS = [
    {
        "name": "rag_search",
        "description": (
            "Search the knowledge base for information about products, services, policies, "
            "or anything the visitor is asking about. Always call this before answering a "
            "factual question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, max 500 characters",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "capture_lead",
        "description": (
            "Record the visitor's contact information when they want to be contacted, "
            "request a demo, or make a purchase inquiry. Call this as soon as the visitor "
            "provides their name and contact details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Visitor name, max 255 characters",
                },
                "contact": {
                    "type": "string",
                    "description": "Email address or E.164 phone number, max 255 characters",
                },
                "intent": {
                    "type": "string",
                    "description": "What the visitor wants, max 1000 characters",
                },
            },
            "required": ["name", "contact", "intent"],
        },
    },
    {
        "name": "escalate",
        "description": (
            "Hand the conversation to a human agent. Use this when the visitor is frustrated, "
            "the issue is too complex, or they explicitly ask to speak with a person."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why escalation is needed, max 500 characters",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "The session UUID",
                },
            },
            "required": ["reason", "conversation_id"],
        },
    },
]


async def _dispatch(
    name: str,
    inputs: dict,
    tenant_id: uuid.UUID,
    session_id: str,
    session: AsyncSession,
    redis: aioredis.Redis,
    embeddings_client: EmbeddingsClient,
) -> str:
    """Route a tool call to the matching Python function. Returns JSON string."""
    from app.tools.rag_search import rag_search
    from app.tools.capture_lead import capture_lead
    from app.tools.escalate import escalate

    if name == "rag_search":
        result = await rag_search(
            query=inputs.get("query", ""),
            tenant_id=tenant_id,
            session=session,
            embeddings_client=embeddings_client,
        )
    elif name == "capture_lead":
        result = await capture_lead(
            name=inputs.get("name", ""),
            contact=inputs.get("contact", ""),
            intent=inputs.get("intent", ""),
            tenant_id=tenant_id,
            session_id=session_id,
            session=session,
            redis=redis,
        )
    elif name == "escalate":
        result = await escalate(
            reason=inputs.get("reason", ""),
            conversation_id=inputs.get("conversation_id", session_id),
            tenant_id=tenant_id,
            session=session,
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result)


def _build_tool_list(enabled: list[str]) -> list[dict]:
    enabled_set = set(enabled)
    return [t for t in _ALL_TOOLS if t["name"] in enabled_set]


async def run_agent(
    message: str,
    tenant_id: uuid.UUID,
    session_id: str,
    history: list[dict],
    session: AsyncSession,
    redis: aioredis.Redis,
    llm_client: LLMClient,
    embeddings_client: EmbeddingsClient,
    agent_config: AgentConfig,
    system_prompt: str,
    max_iterations: int | None = None,
) -> str:
    """Bounded tool-calling loop.

    Hard cap: min(agent_config.max_tool_iterations, _MAX_ITERATIONS_CAP).
    max_iterations overrides the config cap when the caller forces a tighter limit
    (e.g. direct lead/escalate workflows use max_iterations=1).
    """
    config_cap = min(agent_config.max_tool_iterations, _MAX_ITERATIONS_CAP)
    effective_cap = min(max_iterations, config_cap) if max_iterations is not None else config_cap

    active_tools = _build_tool_list(agent_config.enabled_tools)

    # Build message list: system + chronological history + current user message
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    for iteration in range(effective_cap):
        response = await llm_client.complete(
            messages=messages,
            tools=active_tools or None,
            max_tokens=2048,
            tenant_id=tenant_id,
        )
        await record_llm_usage(
            session, tenant_id,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )

        if response.stop_reason == "end_turn" or not response.tool_use:
            return response.content

        # Append the assistant turn (may include text + tool_use content blocks)
        messages.append({"role": "assistant", "content": response.raw_content})

        tool_result_str = await _dispatch(
            name=response.tool_use["name"],
            inputs=response.tool_use["input"],
            tenant_id=tenant_id,
            session_id=session_id,
            session=session,
            redis=redis,
            embeddings_client=embeddings_client,
        )

        # Tool result in Anthropic's required format
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": response.tool_use["id"],
                    "content": tool_result_str,
                }
            ],
        })

    log.warning(
        "agent_iteration_cap_reached",
        tenant_id=str(tenant_id),
        session_id=session_id,
        cap=effective_cap,
    )
    return (
        "I wasn't able to fully resolve your request in this session. "
        "Please try rephrasing or contact us directly for further assistance."
    )
