# Owner C

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Secret/credential patterns — always applied via regex (fast, deterministic)
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
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

# Keep PATTERNS as alias for backward compat
PATTERNS = SECRET_PATTERNS

SECRET_ENTITY_LABELS = {
    "[REDACTED-ANTHROPIC-KEY]": "API_KEY",
    "[REDACTED-APIKEY]": "API_KEY",
    "[REDACTED-TOKEN]": "TOKEN",
    "[REDACTED-GITHUBTOKEN]": "TOKEN",
    "[REDACTED-AWSKEY]": "API_KEY",
    "[REDACTED-EMAIL]": "EMAIL",
    "[REDACTED-PHONE]": "PHONE",
}


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    detected_entities: list[str]
    flags: list[str]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def redact(text: str | None) -> str:
    return PresidioRedactor().redact(text).redacted_text


class PresidioRedactor:
    """
    PII/secret redactor.

    Strategy (order matters):
    1. Run regex patterns for secrets + email + phone → produces [REDACTED-*] tokens
    2. Run Presidio AnalyzerEngine on partially-redacted text for PERSON names only
       (email/phone already handled by step 1 so no double-replacement)
    3. On Presidio init failure: steps 1 only (regex-only fallback)
    """

    def __init__(self) -> None:
        self._analyzer: Any | None = None
        self._anonymizer: Any | None = None
        self._operator_config: Any | None = None
        self._presidio_ready = False
        self._load_presidio()

    def _load_presidio(self) -> None:
        try:
            import spacy
            from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
            from presidio_analyzer.nlp_engine import SpacyNlpEngine
            from presidio_anonymizer import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig

            class _SmEngine(SpacyNlpEngine):
                def __init__(self) -> None:  # type: ignore[override]
                    self.nlp = {"en": spacy.load("en_core_web_sm")}
                    self.nlp_artifacts_cache: dict[str, Any] = {}
                    self.spacy_model_name = "en_core_web_sm"

            nlp_engine = _SmEngine()
            registry = RecognizerRegistry()
            registry.load_predefined_recognizers(nlp_engine=nlp_engine)
            self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)
            self._anonymizer = AnonymizerEngine()
            self._operator_config = OperatorConfig
            self._presidio_ready = True
        except Exception:
            self._presidio_ready = False

    def redact(self, text: str | None) -> RedactionResult:
        if not text:
            return RedactionResult(redacted_text="", detected_entities=[], flags=[])

        # Step 1: regex — secrets + email + phone
        redacted, secret_entities = self._redact_secrets(text)

        # Step 2: Presidio for PERSON names (email/phone already gone from text)
        redacted, pii_entities = self._redact_persons(redacted)

        all_entities = _unique(secret_entities + pii_entities)
        flags = ["pii"] if all_entities else []
        return RedactionResult(
            redacted_text=redacted,
            detected_entities=all_entities,
            flags=flags,
        )

    def _redact_secrets(self, text: str) -> tuple[str, list[str]]:
        redacted = text
        entities: list[str] = []
        for pattern, replacement in SECRET_PATTERNS:
            if pattern.search(redacted):
                entities.append(SECRET_ENTITY_LABELS.get(replacement, "SECRET"))
            redacted = pattern.sub(replacement, redacted)
        return redacted, _unique(entities)

    def _redact_persons(self, text: str) -> tuple[str, list[str]]:
        if not (self._presidio_ready and self._analyzer and self._anonymizer):
            return text, []
        try:
            results = self._analyzer.analyze(text=text, language="en", entities=["PERSON"])
            if not results:
                return text, []
            operators = {"PERSON": self._operator_config("replace", {"new_value": "<PERSON>"})}
            anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
            return anonymized.text, ["PERSON"]
        except Exception:
            return text, []
