# Owner B — backend/evals/classifier/run.py
#
# Classifier eval runner. Calls POST /classify_raw on the modelserver for each
# example in classifier/golden.jsonl and computes macro-F1 plus per-class F1.
# /classify_raw returns the model's top class WITHOUT the runtime confidence
# threshold, so this eval measures model quality rather than the post-threshold
# routing decision (production still uses /classify with the 0.80 gate).
# Exits 1 if macro-F1 is below the threshold in eval_thresholds.yaml.
#
# Threshold: classifier.macro_f1 (from eval_thresholds.yaml; starts at 0.0,
# raised after real training data lands — see eval_thresholds.yaml comments).
#
# Required env vars (live mode):
#   MODELSERVER_URL     — e.g. http://localhost:8001  (default)
#   MODELSERVER_TOKEN   — service bearer token from Vault
#
# Optional env vars:
#   THRESHOLDS_FILE     — path to eval_thresholds.yaml (default: project root)
#
# Usage:
#   python run.py --dry-run          # validate golden.jsonl only
#   python run.py --live             # call modelserver and compute F1

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = BASE_DIR / "golden.jsonl"
REQUIRED_FIELDS = {"id", "message", "expected_intent"}
ALL_INTENTS = ["faq", "lead", "escalate", "spam", "ambiguous"]


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Example:
    id: str
    message: str
    expected_intent: str


@dataclass
class PredictionResult:
    example_id: str
    message: str
    expected: str
    predicted: str
    confidence: float
    correct: bool


@dataclass
class ClassifierEvalResult:
    predictions: list[PredictionResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.predictions)

    @property
    def accuracy(self) -> float:
        return sum(1 for p in self.predictions if p.correct) / self.total if self.total else 0.0

    def per_class_f1(self) -> dict[str, float]:
        classes = {p.expected for p in self.predictions} | {p.predicted for p in self.predictions}
        scores: dict[str, float] = {}
        for cls in classes:
            tp = sum(1 for p in self.predictions if p.expected == cls and p.predicted == cls)
            fp = sum(1 for p in self.predictions if p.expected != cls and p.predicted == cls)
            fn = sum(1 for p in self.predictions if p.expected == cls and p.predicted != cls)
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            scores[cls] = (2 * precision * recall / (precision + recall)
                           if (precision + recall) else 0.0)
        return scores

    def macro_f1(self) -> float:
        scores = self.per_class_f1()
        present = [cls for cls in ALL_INTENTS if cls in scores]
        return sum(scores[c] for c in present) / len(present) if present else 0.0


# ── Golden set validation ─────────────────────────────────────────────────────

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
            examples.append(Example(
                id=row["id"],
                message=row["message"],
                expected_intent=row["expected_intent"],
            ))
    return examples


def dry_run(examples: list[Example]) -> int:
    print(f"golden.jsonl valid — {len(examples)} examples")
    counts: dict[str, int] = defaultdict(int)
    for ex in examples:
        counts[ex.expected_intent] += 1
    for intent in ALL_INTENTS:
        if intent in counts:
            print(f"  {intent}: {counts[intent]}")
    return 0


# ── Threshold loading ─────────────────────────────────────────────────────────

def _load_threshold() -> float:
    """Load the classifier macro-F1 gate. Fail loudly if it can't be read.

    A missing/unreadable thresholds file must NOT silently fall back to 0.0:
    a 0.0 gate passes any model and turns the CI check into a rubber stamp
    (observed when the eval runs in-container without eval_thresholds.yaml present).
    """
    thresholds_file = os.environ.get(
        "THRESHOLDS_FILE",
        str(Path(__file__).resolve().parents[3] / "eval_thresholds.yaml"),
    )
    if not os.path.exists(thresholds_file):
        raise FileNotFoundError(
            f"thresholds file not found: {thresholds_file}. "
            "Set THRESHOLDS_FILE or mount eval_thresholds.yaml into the eval environment. "
            "Refusing to default to 0.0 (that would disable the CI gate)."
        )
    import yaml  # type: ignore[import]
    with open(thresholds_file) as f:
        data = yaml.safe_load(f)
    classifier_cfg = (data or {}).get("classifier") or {}
    if "macro_f1" not in classifier_cfg:
        raise KeyError(
            f"classifier.macro_f1 missing from {thresholds_file}. "
            "Refusing to default to 0.0 (that would disable the CI gate)."
        )
    return float(classifier_cfg["macro_f1"])


# ── Live runner ───────────────────────────────────────────────────────────────

def _classify_one(client, message: str, url: str, token: str,
                  tenant_id: str) -> tuple[str, float]:
    resp = client.post(
        f"{url}/classify_raw",
        json={"text": message, "tenant_id": tenant_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("intent", "ambiguous"), float(data.get("confidence", 0.0))


def run_live(examples: list[Example]) -> ClassifierEvalResult:
    import httpx

    modelserver_url = os.environ.get("MODELSERVER_URL", "http://localhost:8001")
    modelserver_token = os.environ.get("MODELSERVER_TOKEN", "")
    tenant_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    result = ClassifierEvalResult()

    with httpx.Client(timeout=15) as client:
        for ex in examples:
            print(f"  [{ex.id}] {ex.message[:50]!r:<52}", end=" ", flush=True)
            try:
                predicted, confidence = _classify_one(
                    client, ex.message, modelserver_url, modelserver_token, tenant_id
                )
            except Exception as exc:
                print(f"ERROR {exc}")
                result.predictions.append(PredictionResult(
                    example_id=ex.id, message=ex.message,
                    expected=ex.expected_intent, predicted="error",
                    confidence=0.0, correct=False,
                ))
                continue

            correct = predicted == ex.expected_intent
            result.predictions.append(PredictionResult(
                example_id=ex.id, message=ex.message,
                expected=ex.expected_intent, predicted=predicted,
                confidence=confidence, correct=correct,
            ))
            mark = "PASS" if correct else f"FAIL  expected={ex.expected_intent} got={predicted}"
            print(f"{mark}  conf={confidence:.2f}")

    return result


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Classifier eval runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--live", action="store_true")
    args = parser.parse_args()

    examples = load_golden()

    if args.dry_run:
        return dry_run(examples)

    threshold = _load_threshold()
    print(f"classifier eval  examples={len(examples)}  threshold macro-F1={threshold:.2f}")

    result = run_live(examples)

    macro = result.macro_f1()
    per_class = result.per_class_f1()

    print(f"\naccuracy={result.accuracy:.0%}  macro-F1={macro:.3f}  threshold={threshold:.3f}")
    print("\nper-class F1:")
    for intent in ALL_INTENTS:
        f1 = per_class.get(intent, 0.0)
        count = sum(1 for p in result.predictions if p.expected == intent)
        print(f"  {intent:<12} F1={f1:.3f}  n={count}")

    errors = [p for p in result.predictions if not p.correct and p.predicted != "error"]
    if errors:
        print(f"\nwrong predictions ({len(errors)}):")
        for p in errors:
            print(f"  [{p.example_id}] expected={p.expected} got={p.predicted}  {p.message[:50]!r}")

    if macro < threshold:
        print(f"\nFAIL — macro-F1 {macro:.3f} below threshold {threshold:.3f}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
