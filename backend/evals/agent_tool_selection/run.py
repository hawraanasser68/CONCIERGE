# Owner B — backend/evals/agent_tool_selection/run.py
#
# Agent tool-selection eval runner. Sends each golden example to POST
# /api/v1/chat/message and infers which tool was used from the response text
# and (optionally) DB artifact checks (Lead / Escalation rows created).
#
# Threshold: agent.tool_accuracy >= 0.80 (12/15 correct) from eval_thresholds.yaml.
#
# Required env vars (live mode):
#   CONCIERGE_BASE_URL   — e.g. http://localhost:8000  (default)
#   WIDGET_TOKEN         — pre-generated widget JWT for Tenant A
#
# Optional env vars:
#   DATABASE_URL         — enables DB-based artifact checks for capture_lead / escalate
#   THRESHOLDS_FILE      — path to eval_thresholds.yaml (default: project root)
#
# Usage:
#   python run.py --dry-run          # validate golden.jsonl format only
#   python run.py --live             # run against live stack

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = BASE_DIR / "golden.jsonl"
REQUIRED_FIELDS = {"id", "message", "category"}

_CAPTURE_LEAD_SIGNALS = {
    "recorded", "noted", "captured", "saved your", "get back to you",
    "contact details", "pass your", "reach out", "follow up", "details have been",
}
_ESCALATE_SIGNALS = {
    "escalat", "connect you", "human", "someone from our team",
    "pass this", "transfer", "colleague", "speak with", "ticket",
}
_RAG_SIGNALS = {
    "hour", "deliver", "price", "cost", "$", "policy", "subscription",
    "bouquet", "wedding", "arrangement", "monday", "sunday", "loyalty",
    "am", "pm", "open", "closed",
}


@dataclass
class Example:
    id: str
    message: str
    category: str
    expected_tool: str | None
    expected_tools: list[str]
    should_not_use: list[str]

    @property
    def all_expected(self) -> list[str]:
        return self.expected_tools if self.expected_tools else (
            [self.expected_tool] if self.expected_tool else []
        )


@dataclass
class ExampleResult:
    example_id: str
    passed: bool
    predicted_tools: list[str]
    expected_tools: list[str]
    reason: str


@dataclass
class EvalResult:
    results: list[ExampleResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def accuracy(self) -> float:
        return self.passed_count / self.total if self.total else 0.0

    def passes_threshold(self, threshold: float) -> bool:
        return self.accuracy >= threshold


def _load_threshold() -> float:
    thresholds_file = os.environ.get(
        "THRESHOLDS_FILE",
        str(Path(__file__).resolve().parents[3] / "eval_thresholds.yaml"),
    )
    try:
        import yaml  # type: ignore[import]
        with open(thresholds_file) as f:
            data = yaml.safe_load(f)
        return float(data.get("agent", {}).get("tool_accuracy", 0.80))
    except Exception:
        return 0.80


def load_golden(path: Path = GOLDEN_PATH) -> list[Example]:
    examples: list[Example] = []
    with path.open() as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno} invalid JSON: {e}") from e
            missing = REQUIRED_FIELDS - set(row)
            if missing:
                raise ValueError(
                    f"{path}:{lineno} id={row.get('id')} missing fields: {sorted(missing)}"
                )
            if "expected_tool" not in row and "expected_tools" not in row:
                raise ValueError(
                    f"{path}:{lineno} id={row['id']} must have expected_tool or expected_tools"
                )
            examples.append(Example(
                id=row["id"],
                message=row["message"],
                category=row["category"],
                expected_tool=row.get("expected_tool"),
                expected_tools=row.get("expected_tools", []),
                should_not_use=row.get("should_not_use", []),
            ))
    return examples


def dry_run(examples: list[Example]) -> int:
    print(f"golden.jsonl valid — {len(examples)} examples")
    counts: dict[str, int] = {}
    for ex in examples:
        counts[ex.category] = counts.get(ex.category, 0) + 1
    for cat, n in sorted(counts.items()):
        print(f"  {cat}: {n}")
    return 0


def _infer_tools_from_response(response_text: str) -> list[str]:
    text = response_text.lower()
    tools: list[str] = []
    if any(sig in text for sig in _CAPTURE_LEAD_SIGNALS):
        tools.append("capture_lead")
    if any(sig in text for sig in _ESCALATE_SIGNALS):
        tools.append("escalate")
    if any(sig in text for sig in _RAG_SIGNALS):
        tools.append("rag_search")
    return tools


def _check_db_artifacts(session_id: str, tenant_id: str, db_url: str) -> dict[str, bool]:
    try:
        import asyncio
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        async def _q() -> dict[str, bool]:
            engine = create_async_engine(db_url, echo=False)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as sess:
                await sess.execute(
                    text("SELECT set_config('app.tenant_id', :tid, TRUE)"),
                    {"tid": tenant_id},
                )
                lead_n = (await sess.execute(
                    text("SELECT COUNT(*) FROM leads WHERE session_id = :sid AND tenant_id = :tid::uuid"),
                    {"sid": session_id, "tid": tenant_id},
                )).scalar()
                esc_n = (await sess.execute(
                    text("SELECT COUNT(*) FROM escalations WHERE session_id = :sid AND tenant_id = :tid::uuid"),
                    {"sid": session_id, "tid": tenant_id},
                )).scalar()
            await engine.dispose()
            return {"capture_lead": bool(lead_n), "escalate": bool(esc_n)}

        return asyncio.run(_q())
    except Exception as exc:
        print(f"  [warn] DB check skipped: {exc}", file=sys.stderr)
        return {}


def run_live(examples: list[Example]) -> tuple[EvalResult, float]:
    import httpx

    base_url = os.environ.get("CONCIERGE_BASE_URL", "http://localhost:8000")
    widget_token = os.environ.get("WIDGET_TOKEN", "")
    db_url = os.environ.get("DATABASE_URL", "")
    tenant_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    threshold = _load_threshold()

    if not widget_token:
        print("ERROR: set WIDGET_TOKEN env var to a valid Tenant A widget JWT", file=sys.stderr)
        sys.exit(2)

    result = EvalResult()

    with httpx.Client(base_url=base_url, timeout=30) as client:
        for ex in examples:
            session_id = str(uuid.uuid4())
            print(f"  [{ex.id}] {ex.message[:55]!r:<57}", end=" ", flush=True)

            try:
                resp = client.post(
                    "/api/v1/chat/message",
                    json={"message": ex.message},
                    headers={
                        "Authorization": f"Bearer {widget_token}",
                        "X-Session-Id": session_id,
                        "Origin": "http://localhost:3000",
                    },
                )
                resp.raise_for_status()
                response_text = resp.json().get("response", "")
            except Exception as exc:
                result.results.append(ExampleResult(
                    example_id=ex.id, passed=False,
                    predicted_tools=[], expected_tools=ex.all_expected,
                    reason=f"HTTP error: {exc}",
                ))
                print("ERROR")
                continue

            predicted = _infer_tools_from_response(response_text)
            if db_url:
                for tool, hit in _check_db_artifacts(session_id, tenant_id, db_url).items():
                    if hit and tool not in predicted:
                        predicted.append(tool)

            expected = ex.all_expected
            bad = [t for t in ex.should_not_use if t in predicted]

            if ex.category == "multi":
                missing = [e for e in expected if e not in predicted]
                passed = not missing and not bad
                reason = "ok" if passed else f"missing={missing} bad={bad}"
            else:
                passed = bool(expected) and expected[0] in predicted and not bad
                reason = "ok" if passed else f"predicted={predicted} expected={expected} bad={bad}"

            result.results.append(ExampleResult(
                example_id=ex.id, passed=passed,
                predicted_tools=predicted, expected_tools=expected,
                reason=reason,
            ))
            print("PASS" if passed else f"FAIL  {reason}")

    return result, threshold


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent tool-selection eval runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--live", action="store_true")
    args = parser.parse_args()

    examples = load_golden()

    if args.dry_run:
        return dry_run(examples)

    threshold = _load_threshold()
    print(f"agent tool-selection eval  examples={len(examples)}  threshold={threshold:.0%}")
    result, threshold = run_live(examples)

    print(f"\n{result.passed_count}/{result.total} correct ({result.accuracy:.0%})  "
          f"threshold={threshold:.0%}")

    if not result.passes_threshold(threshold):
        print(f"FAIL — accuracy {result.accuracy:.0%} below threshold {threshold:.0%}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
