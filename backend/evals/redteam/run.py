# Owner C

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INJECTION_PATH = BASE_DIR / "injection.jsonl"
DEFAULT_CROSS_TENANT_PATH = BASE_DIR / "cross_tenant.jsonl"
INJECTION_REQUIRED_FIELDS = {"id", "message", "expected_blocked", "expected_category"}
CROSS_TENANT_REQUIRED_FIELDS = {"id", "description", "setup", "expected"}


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


def _require_non_empty_string(row: dict[str, Any], field: str, case_id: str, failures: list[str]) -> None:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        failures.append(f"{case_id} field {field!r} must be a non-empty string")


def validate_injection_cases(path: Path = DEFAULT_INJECTION_PATH) -> EvalResult:
    failures: list[str] = []
    rows = _load_jsonl(path)

    for line_number, row in rows:
        case_id = str(row.get("id", f"{path}:{line_number}"))
        missing = INJECTION_REQUIRED_FIELDS - set(row)
        if missing:
            failures.append(f"{case_id} missing fields: {sorted(missing)}")
            continue

        _require_non_empty_string(row, "id", case_id, failures)
        _require_non_empty_string(row, "message", case_id, failures)
        _require_non_empty_string(row, "expected_category", case_id, failures)
        if row.get("expected_blocked") is not True:
            failures.append(f"{case_id} expected_blocked must be true")

    return EvalResult(total=len(rows), failures=failures)


def validate_cross_tenant_cases(path: Path = DEFAULT_CROSS_TENANT_PATH) -> EvalResult:
    failures: list[str] = []
    rows = _load_jsonl(path)

    for line_number, row in rows:
        case_id = str(row.get("id", f"{path}:{line_number}"))
        missing = CROSS_TENANT_REQUIRED_FIELDS - set(row)
        if missing:
            failures.append(f"{case_id} missing fields: {sorted(missing)}")
            continue

        for field in CROSS_TENANT_REQUIRED_FIELDS:
            _require_non_empty_string(row, field, case_id, failures)

    return EvalResult(total=len(rows), failures=failures)


def validate_all(
    injection_path: Path = DEFAULT_INJECTION_PATH,
    cross_tenant_path: Path = DEFAULT_CROSS_TENANT_PATH,
) -> EvalResult:
    injection = validate_injection_cases(injection_path)
    cross_tenant = validate_cross_tenant_cases(cross_tenant_path)
    return EvalResult(
        total=injection.total + cross_tenant.total,
        failures=injection.failures + cross_tenant.failures,
    )


def main() -> int:
    result = validate_all()
    if result.passed:
        print(f"red-team fixture validation passed: {result.total} cases")
        return 0

    print(f"red-team fixture validation failed: {len(result.failures)} failures across {result.total} cases")
    for failure in result.failures:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
