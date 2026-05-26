# Owner B — backend/app/services/llm_client.py
#
# Anthropic SDK adapter for claude-sonnet-4-6. Handles system-message extraction
# (peels a leading role="system" entry and passes it as the SDK's system= param),
# optional tool schema injection, and content-block parsing. Returns a normalised
# LLMResponse with stop_reason, joined text content, tool_use dict, usage counts,
# and raw_content blocks — the last field lets agent.py re-append the assistant
# turn verbatim in Anthropic's multi-turn format.
#
# Usage (from agent.py and router.py workflows):
#   llm = get_llm_client(request)
#   resp = await llm.complete(messages, tools=schemas, max_tokens=2048)

import uuid
from dataclasses import dataclass

import anthropic
import structlog
from fastapi import Request

log = structlog.get_logger()

_MODEL = "claude-sonnet-4-6"


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    stop_reason: str          # "end_turn" | "tool_use"
    content: str              # joined text blocks (empty when stop_reason is "tool_use")
    tool_use: dict | None     # {"id": "...", "name": "...", "input": {...}} or None
    usage: Usage
    raw_content: list[dict]   # serialised content blocks — append directly to messages in agent loop


class LLMClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
        tenant_id: uuid.UUID | None = None,  # reserved for cost attribution by the caller
    ) -> LLMResponse:
        # If the first message is a system turn, peel it off — Anthropic API takes system
        # as a separate parameter, not as a message role.
        api_messages = messages
        kwargs: dict = {"model": _MODEL, "max_tokens": max_tokens}

        if messages and messages[0].get("role") == "system":
            kwargs["system"] = messages[0]["content"]
            api_messages = messages[1:]

        kwargs["messages"] = api_messages

        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_use_block: dict | None = None
        raw_content: list[dict] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                raw_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_use_block = {"id": block.id, "name": block.name, "input": block.input}
                raw_content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )

        return LLMResponse(
            stop_reason=response.stop_reason,
            content="".join(text_parts),
            tool_use=tool_use_block,
            usage=Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            raw_content=raw_content,
        )


def get_llm_client(request: Request) -> LLMClient:
    return LLMClient(api_key=request.app.state.llm_api_key)
