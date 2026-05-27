# Owner C

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


LOGGER = logging.getLogger("guardrails.tenant_rails")
BLOCK_REASON = "Request blocked by tenant safety policy."

_tenant_config_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class TenantRailsDecision:
    allowed: bool
    flags: list[str] = field(default_factory=list)
    block_reason: str | None = None
    matched_rules: list[str] = field(default_factory=list)


def _fetch_tenant_config(tenant_id: str, backend_base_url: str, service_token: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = _tenant_config_cache.get(tenant_id)
    if cached is not None:
        timestamp, config = cached
        if now - timestamp < _CACHE_TTL_SECONDS:
            return config

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{backend_base_url}/api/v1/admin/agent-config",
                headers={
                    "Authorization": f"Bearer {service_token}",
                    "X-Tenant-Id": tenant_id,
                },
            )
            resp.raise_for_status()
            config = resp.json()
    except Exception as exc:
        LOGGER.warning("tenant_config_fetch_failed tenant_id=%s error=%s", tenant_id, exc)
        config = {}

    _tenant_config_cache[tenant_id] = (now, config)
    return config


def evaluate_tenant_rails(
    message: str,
    tenant_config: dict[str, Any],
) -> TenantRailsDecision:
    matched_rules: list[str] = []
    flagged: list[str] = []
    message_lower = message.lower()

    blocked_topics: list[str] = tenant_config.get("blocked_topics", [])
    for topic in blocked_topics:
        if topic.lower() in message_lower:
            matched_rules.append(f"blocked_topic:{topic}")
            flagged.append("off_topic")
            break

    forbidden_phrases: list[str] = tenant_config.get("forbidden_phrases", [])
    for phrase in forbidden_phrases:
        if phrase.lower() in message_lower:
            matched_rules.append(f"forbidden_phrase:{phrase}")
            if "off_topic" not in flagged:
                flagged.append("off_topic")
            break

    allowed_topics: list[str] = tenant_config.get("allowed_topics", [])
    if allowed_topics and not matched_rules:
        on_topic = any(topic.lower() in message_lower for topic in allowed_topics)
        if not on_topic:
            matched_rules.append("off_topic:not_in_allowed_topics")
            flagged.append("off_topic")

    is_blocked = len(matched_rules) > 0
    return TenantRailsDecision(
        allowed=not is_blocked,
        flags=flagged,
        block_reason=BLOCK_REASON if is_blocked else None,
        matched_rules=matched_rules,
    )


def evaluate_persona_compliance(response_text: str, persona_name: str | None) -> bool:
    if not persona_name:
        return True
    text_lower = response_text.lower()
    persona_lower = persona_name.lower()
    ai_identifiers = ["i am claude", "i'm claude", "i am gpt", "i'm gpt", "i am an ai", "i'm an ai"]
    for identifier in ai_identifiers:
        if identifier in text_lower and persona_lower not in text_lower:
            return False
    return True
