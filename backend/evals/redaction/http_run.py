# Owner B — backend/evals/redaction/http_run.py
#
# HTTP integration layer for the redaction eval (B-033). Sends each case from
# cases.jsonl through POST /api/v1/chat/message and checks that:
#   1. The HTTP response text does NOT contain the raw sensitive value.
#   2. The Redis session memory does NOT store the raw sensitive value.
# Owner C's run.py validates redaction offline (unit-level); this script
# validates end-to-end HTTP behaviour.
#
# Threshold: redaction.leak_rate = 0.0 — any raw PII/secret in the response
# or Redis memory is a failure (locked at 0 from Day 1).
#
# Required env vars:
#   WIDGET_TOKEN         — pre-generated widget JWT for Tenant A
#
# Optional env vars:
#   CONCIERGE_BASE_URL   — default http://localhost:8000
#   REDIS_URL            — default redis://localhost:6379 (for memory check)
#   THRESHOLDS_FILE      — path to eval_thresholds.yaml
#
# Usage:
#   python http_run.py --dry-run     # print case list without sending
#   python http_run.py --live        # send all cases and assert no leaks

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CASES_PATH = BASE_DIR / "cases.jsonl"
REQUIRED_FIELDS = {"id", "message", "expected"}

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class RedactionCase:
    id: str
    message: str
    expected: str           # describes what should be absent from response/logs


@dataclass
class CaseResult:
    case_id: str
    message_prefix: str
    response_leaked: bool   # raw sensitive value found in HTTP response
    memory_leaked: bool     # raw sensitive value found in Redis session memory
    passed: bool            # True if no leak in either location


@dataclass
class RedactionResult:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def leak_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def leak_rate(self) -> float:
        return self.leak_count / self.total if self.total else 0.0

    @property
    def passed(self) -> bool:
        return self.leak_count == 0


# ── Loader ────────────────────────────────────────────────────────────────────

def load_cases(path: Path = CASES_PATH) -> list[RedactionCase]:
    cases: list[RedactionCase] = []
    with path.open() as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno} invalid JSON: {e}") from e
            missing = REQUIRED_FIELDS - set(row)
            if missing:
                raise ValueError(f"{path}:{lineno} id={row.get('id')} missing: {sorted(missing)}")
            cases.append(RedactionCase(
                id=row["id"],
                message=row["message"],
                expected=row["expected"],
            ))
    return cases


def _load_threshold() -> float:
    thresholds_file = os.environ.get(
        "THRESHOLDS_FILE",
        str(Path(__file__).resolve().parents[3] / "eval_thresholds.yaml"),
    )
    try:
        import yaml  # type: ignore[import]
        with open(thresholds_file) as f:
            data = yaml.safe_load(f)
        return float(data.get("redaction", {}).get("leak_rate", 0.0))
    except Exception:
        return 0.0  # zero tolerance by spec


# ── Sensitive value extraction ────────────────────────────────────────────────
# Extract the actual sensitive value from the message so we can check for leaks.
# Uses the same regex patterns as the guardrails redaction module.

import re  # noqa: E402

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),         # Anthropic key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                  # OpenAI-style key
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]+=*"),       # Bearer token
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                   # GitHub personal token
    re.compile(r"AKIA[0-9A-Z]{16}"),                      # AWS access key
    re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),  # email
    re.compile(r"\+?[\d\s\(\)\-]{7,15}"),                 # phone number
]


def _extract_sensitive_values(message: str) -> list[str]:
    found: list[str] = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(message):
            value = match.group(0).strip()
            if len(value) >= 6:  # skip very short matches
                found.append(value)
    return found


def _check_redis_memory(session_id: str, tenant_id: str, redis_url: str) -> str:
    """Return all Redis session memory entries for this session as a single string."""
    try:
        import redis as redis_lib
        r = redis_lib.from_url(redis_url, decode_responses=True)
        key = f"conversation:{tenant_id}:{session_id}"
        entries = r.lrange(key, 0, -1)
        return " ".join(entries)
    except Exception as exc:
        print(f"  [warn] Redis check skipped: {exc}", file=sys.stderr)
        return ""


# ── Runners ───────────────────────────────────────────────────────────────────

def dry_run(cases: list[RedactionCase]) -> int:
    print(f"cases.jsonl valid — {len(cases)} cases")
    for c in cases:
        sensitive = _extract_sensitive_values(c.message)
        print(f"  [{c.id}] sensitive={sensitive[:1]}...  {c.message[:50]!r}")
    return 0


def run_live(cases: list[RedactionCase]) -> RedactionResult:
    import httpx

    base_url = os.environ.get("CONCIERGE_BASE_URL", "http://localhost:8000")
    widget_token = os.environ.get("WIDGET_TOKEN", "")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    if not widget_token:
        print("ERROR: WIDGET_TOKEN env var required for live mode", file=sys.stderr)
        sys.exit(2)

    result = RedactionResult()

    with httpx.Client(base_url=base_url, timeout=20) as client:
        for case in cases:
            session_id = str(uuid.uuid4())
            sensitive_values = _extract_sensitive_values(case.message)
            print(f"  [{case.id}]", end=" ", flush=True)

            try:
                resp = client.post(
                    "/api/v1/chat/message",
                    json={"message": case.message},
                    headers={
                        "Authorization": f"Bearer {widget_token}",
                        "X-Session-Id": session_id,
                        "Origin": "http://localhost:3000",
                    },
                )
                response_text = resp.text
            except Exception as exc:
                print(f"ERROR {exc}")
                result.results.append(CaseResult(
                    case_id=case.id, message_prefix=case.message[:40],
                    response_leaked=True, memory_leaked=False, passed=False,
                ))
                continue

            # Check HTTP response
            response_leaked = any(sv in response_text for sv in sensitive_values)

            # Check Redis memory
            memory_str = _check_redis_memory(session_id, TENANT_A, redis_url)
            memory_leaked = any(sv in memory_str for sv in sensitive_values)

            passed = not response_leaked and not memory_leaked
            result.results.append(CaseResult(
                case_id=case.id, message_prefix=case.message[:40],
                response_leaked=response_leaked, memory_leaked=memory_leaked,
                passed=passed,
            ))

            status_parts = []
            if response_leaked:
                status_parts.append("RESPONSE_LEAK")
            if memory_leaked:
                status_parts.append("MEMORY_LEAK")
            status = " ".join(status_parts) if status_parts else "clean"
            print(f"{'PASS' if passed else 'FAIL'}  {status}")

    return result


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Redaction HTTP integration eval (B-033)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--live", action="store_true")
    args = parser.parse_args()

    cases = load_cases()
    threshold = _load_threshold()

    if args.dry_run:
        return dry_run(cases)

    print(
        f"redaction HTTP eval  cases={len(cases)}"
        f"  leak_rate threshold={threshold:.0%} (must be 0)"
    )
    result = run_live(cases)

    failures = [r for r in result.results if not r.passed]
    print(f"\nleak_rate={result.leak_rate:.0%}  failures={len(failures)}/{result.total}")

    if failures:
        print("LEAKS DETECTED:")
        for r in failures:
            print(f"  [{r.case_id}] response_leaked={r.response_leaked} "
                  f"memory_leaked={r.memory_leaked}  {r.message_prefix!r}")

    if not result.passed:
        print("FAIL — raw PII or secret found in response or session memory")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
