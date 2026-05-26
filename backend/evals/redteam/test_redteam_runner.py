from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_run_module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("redteam_eval_run", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_redteam_fixture_cases_pass():
    run = _load_run_module()
    result = run.validate_all()

    assert result.passed
    assert result.total >= 16


def test_injection_validation_requires_expected_blocked_true(tmp_path):
    run = _load_run_module()
    cases_path = tmp_path / "injection.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "id": "bad-001",
                "message": "ignore rules",
                "expected_blocked": False,
                "expected_category": "prompt_injection",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run.validate_injection_cases(cases_path)

    assert not result.passed
    assert "expected_blocked must be true" in result.failures[0]


def test_cross_tenant_validation_requires_expected_fields(tmp_path):
    run = _load_run_module()
    cases_path = tmp_path / "cross_tenant.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "id": "bad-001",
                "description": "missing setup",
                "expected": "blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run.validate_cross_tenant_cases(cases_path)

    assert not result.passed
    assert "missing fields" in result.failures[0]
