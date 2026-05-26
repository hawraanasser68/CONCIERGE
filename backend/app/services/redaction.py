# Owner C

from __future__ import annotations

import re


PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b"), "[REDACTED-ANTHROPIC-KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"), "[REDACTED-APIKEY]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b"), "[REDACTED-TOKEN]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED-GITHUBTOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED-AWSKEY]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED-EMAIL]"),
    (
        re.compile(r"(?<!\w)(?:\+?\d[\d(). -]{7,}\d)(?!\w)"),
        "[REDACTED-PHONE]",
    ),
]


def redact(text: str | None) -> str:
    if not text:
        return ""

    redacted = text
    for pattern, replacement in PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
