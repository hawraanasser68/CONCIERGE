# Owner C

from __future__ import annotations

import re
from dataclasses import dataclass


BLOCK_REASON = "Request blocked by safety policy."
CATEGORY_ORDER = (
    "prompt_injection",
    "cross_tenant_probe",
    "jailbreak",
    "pii",
    "off_topic",
)
BLOCKING_CATEGORIES = {"prompt_injection", "cross_tenant_probe", "jailbreak", "off_topic"}
CATEGORY_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "prompt_injection": (
        re.compile(r"\bignore(?:\s+all)?\s+previous\s+instructions\b", re.IGNORECASE),
        re.compile(r"\bdisregard(?:\s+all)?(?:\s+your)?\s+(?:previous|earlier)\s+(?:instructions|rules)\b", re.IGNORECASE),
        re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
        re.compile(r"\bact\s+as\b", re.IGNORECASE),
        re.compile(r"\brole-?play\s+as\b", re.IGNORECASE),
        re.compile(r"\bsecurity\s+policy\s+does\s+not\s+apply\b", re.IGNORECASE),
    ),
    "cross_tenant_probe": (
        re.compile(r"\bother\s+tenant\b", re.IGNORECASE),
        re.compile(r"\banother\s+tenant\b", re.IGNORECASE),
        re.compile(r"\btenant\s*b\b", re.IGNORECASE),
        re.compile(r"\bother\s+company\s+data\b", re.IGNORECASE),
        re.compile(r"\bshow\s+leads\b", re.IGNORECASE),
        re.compile(r"\banother\s+customer\s+account\b", re.IGNORECASE),
        re.compile(r"\bdata\s+from\s+a\s+different\s+account\b", re.IGNORECASE),
        re.compile(r"\b(?:other|another)\s+compan(?:y|ies)\b", re.IGNORECASE),
        re.compile(r"\bprivate\s+knowledge\s+base\b", re.IGNORECASE),
        re.compile(r"\bignore\s+the\s+tenant\s+boundary\b", re.IGNORECASE),
        re.compile(r"\b(?:hidden|system)\s+prompt\s+for\b", re.IGNORECASE),
        re.compile(r"\binternal\s+instructions\s+for\b", re.IGNORECASE),
    ),
    "jailbreak": (
        # Attempts to extract system prompt, instructions, or guardrails details
        re.compile(
            r"\b(?:reveal|expose|print|output|display)\s+(?:the\s+)?(?:hidden\s+|internal\s+|exact\s+|private\s+)?(?:system\s+prompt|system\s+message|guardrails?\s+checks?|instructions)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bshow\s+me\b.{0,60}(?:hidden|exact|private|internal)\s+(?:system\s+(?:prompt|message)|guardrails?\s+checks?|instructions)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\bprivate\s+guardrails?\b", re.IGNORECASE),
        re.compile(r"\brepeat\s+(?:your\s+)?(?:hidden\s+)?system\s+prompt\b", re.IGNORECASE),
        re.compile(r"\bjailbreak\b", re.IGNORECASE),
        re.compile(r"\bbreak\s+character\b", re.IGNORECASE),
        re.compile(r"\bbypass\s+(?:your\s+)?restrictions\b", re.IGNORECASE),
        re.compile(r"\bdump\s+config\b", re.IGNORECASE),
        re.compile(r"\bdump\s+(?:the\s+)?(?:secret\s+|internal\s+)?instructions\b", re.IGNORECASE),
        re.compile(r"\bdeveloper\s+mode\b", re.IGNORECASE),
        re.compile(r"\banswer\s+freely\b", re.IGNORECASE),
        re.compile(r"\bunrestricted\s+ai\s+assistant\b", re.IGNORECASE),
    ),
}


@dataclass(frozen=True)
class GuardrailsDecision:
    allowed: bool
    flagged_categories: list[str]
    block_reason: str | None = None
    matched_rules: list[str] | None = None


def evaluate_message(message: str, redacted_message: str | None = None) -> GuardrailsDecision:
    matched_rules: list[str] = []
    matched_categories: set[str] = set()
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(message):
                matched_categories.add(category)
                matched_rules.append(category)
                break

    if redacted_message is not None and redacted_message != message:
        matched_categories.add("pii")

    flagged_categories = [category for category in CATEGORY_ORDER if category in matched_categories]
    allowed = not any(category in BLOCKING_CATEGORIES for category in flagged_categories)
    block_reason = None if allowed else BLOCK_REASON
    return GuardrailsDecision(
        allowed=allowed,
        flagged_categories=flagged_categories,
        block_reason=block_reason,
        matched_rules=matched_rules,
    )


def to_rail_result(decision: GuardrailsDecision) -> dict[str, object]:
    return {
        "allowed": decision.allowed,
        "flags": decision.flagged_categories,
        "matched_rules": decision.matched_rules or [],
    }
