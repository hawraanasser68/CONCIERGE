import asyncio
import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _load_module():
    module = importlib.import_module("guardrails.server")
    return importlib.reload(module)


def _fake_request(token="test-token"):
    return SimpleNamespace(
        headers={"Authorization": f"Bearer {token}"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                service_token=token,
            )
        ),
    )


def _payload(module, message: str, direction: str = "input"):
    return module.GuardrailsRequest(
        message=message,
        tenant_id="11111111-1111-1111-1111-111111111111",
        session_id="22222222-2222-2222-2222-222222222222",
        direction=direction,
    )


def test_health_returns_200_payload():
    module = _load_module()

    response = asyncio.run(module.health())

    assert response == {"status": "ok"}


def test_check_input_without_token_returns_401():
    module = _load_module()
    request = _fake_request()
    request.headers = {}

    with pytest.raises(HTTPException) as exc_info:
        module._require_service_token(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "UNAUTHORIZED"


def test_check_output_without_token_returns_401():
    module = _load_module()
    request = _fake_request()
    request.headers = {}

    with pytest.raises(HTTPException) as exc_info:
        module._require_service_token(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "UNAUTHORIZED"


def test_check_input_redacts_secrets_and_pii():
    module = _load_module()
    request = _fake_request()
    payload = _payload(
        module,
        "Email john@example.com call +1 555 123 4567 with sk-ant-secret123456 and Bearer abc.def",
        direction="input",
    )

    response = asyncio.run(module.check_input(payload, request, None))

    assert response["allowed"] is True
    assert response["flagged_categories"] == []
    assert "[REDACTED-EMAIL]" in response["redacted_message"]
    assert "[REDACTED-PHONE]" in response["redacted_message"]
    assert "[REDACTED-ANTHROPIC-KEY]" in response["redacted_message"]
    assert "[REDACTED-TOKEN]" in response["redacted_message"]
    assert "john@example.com" not in response["redacted_message"]


def test_check_output_redacts_secrets_and_pii():
    module = _load_module()
    request = _fake_request()
    payload = _payload(
        module,
        "Reply to jane@example.com using ghp_abcdefghijklmnopqrstuvwxyz123456",
        direction="output",
    )

    response = asyncio.run(module.check_output(payload, request, None))

    assert response["allowed"] is True
    assert response["flagged_categories"] == []
    assert "[REDACTED-EMAIL]" in response["redacted_message"]
    assert "[REDACTED-GITHUBTOKEN]" in response["redacted_message"]
