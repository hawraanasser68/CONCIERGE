# Owner C

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.redaction import PATTERNS, redact


DEFAULT_CASES_PATH = Path(__file__).with_name("cases.jsonl")
REQUIRED_FIELDS = {"id", "message", "expected"}


@dataclass(frozen=True)
class EvalResult:
    total: int
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def _load_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} must be a JSON object")
            rows.append((line_number, value))
    return rows


def _sensitive_matches(text: str) -> list[str]:
    matches: list[str] = []
    for pattern, _ in PATTERNS:
        matches.extend(match.group(0) for match in pattern.finditer(text))
    return matches


def validate_cases(path: Path = DEFAULT_CASES_PATH) -> EvalResult:
    failures: list[str] = []
    rows = _load_jsonl(path)

    for line_number, row in rows:
        missing = REQUIRED_FIELDS - set(row)
        if missing:
            failures.append(f"{path}:{line_number} missing fields: {sorted(missing)}")
            continue

        case_id = str(row["id"])
        message = row["message"]
        if not isinstance(message, str) or not message:
            failures.append(f"{case_id} message must be a non-empty string")
            continue

        sensitive_values = _sensitive_matches(message)
        if not sensitive_values:
            failures.append(f"{case_id} did not contain a recognized fake secret or PII value")
            continue

        redacted = redact(message)
        for sensitive_value in sensitive_values:
            if sensitive_value in redacted:
                failures.append(f"{case_id} left sensitive value unredacted: {sensitive_value}")

    return EvalResult(total=len(rows), failures=failures)


def main() -> int:
    result = validate_cases()
    if result.passed:
        print(f"redaction eval passed: {result.total} cases")
        return 0

    print(f"redaction eval failed: {len(result.failures)} failures across {result.total} cases")
    for failure in result.failures:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
