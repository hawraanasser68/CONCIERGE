from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_run_module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("redaction_eval_run", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_redaction_fixture_cases_pass():
    run = _load_run_module()
    result = run.validate_cases()

    assert result.passed
    assert result.total >= 7


def test_redaction_validation_fails_when_sensitive_value_missing(tmp_path):
    run = _load_run_module()
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "id": "bad-001",
                "message": "Token abc123 is not covered by current patterns.",
                "expected": "should fail because no recognized sensitive value exists",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run.validate_cases(cases_path)

    assert not result.passed
    assert "recognized fake secret or PII" in result.failures[0]
