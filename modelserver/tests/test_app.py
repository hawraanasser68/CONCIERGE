import asyncio
import importlib
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@dataclass
class FakeBundle:
    model: object
    internal_to_contract: dict[str, str]
    runtime_threshold: float
    deployed_model: str
    embedding_name: str


class FakeModel:
    def __init__(self, probabilities):
        self.classes_ = ["spam", "question", "lead", "escalate", "unknown_or_agent"]
        self._probabilities = probabilities

    def predict_proba(self, _rows):
        return [self._probabilities]


def _load_module():
    module = importlib.import_module("modelserver.app")
    return importlib.reload(module)


def _fake_request(module, token="test-token", bundle=None):
    if bundle is None:
        bundle = FakeBundle(
            model=FakeModel([0.9, 0.02, 0.02, 0.03, 0.03]),
            internal_to_contract={
                "spam": "spam",
                "question": "faq",
                "lead": "lead",
                "escalate": "escalate",
                "unknown_or_agent": "ambiguous",
            },
            runtime_threshold=0.8,
            deployed_model="classical",
            embedding_name="bge_small",
        )
    return SimpleNamespace(
        headers={"Authorization": f"Bearer {token}"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                service_token=token,
                classifier_bundle=bundle,
            )
        ),
    )


def test_health_returns_ok_payload():
    module = _load_module()
    request = _fake_request(module)

    response = asyncio.run(module.health(request))

    assert response == {"status": "ok", "classifier": "classical", "embedding": "bge_small"}


def test_classify_without_token_returns_401():
    module = _load_module()
    request = _fake_request(module)
    request.headers = {}

    with pytest.raises(HTTPException) as exc_info:
        module._require_service_token(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "UNAUTHORIZED"


def test_classify_with_token_returns_contract_label():
    module = _load_module()
    bundle = FakeBundle(
        model=FakeModel([0.05, 0.9, 0.02, 0.02, 0.01]),
        internal_to_contract={
            "spam": "spam",
            "question": "faq",
            "lead": "lead",
            "escalate": "escalate",
            "unknown_or_agent": "ambiguous",
        },
        runtime_threshold=0.8,
        deployed_model="classical",
        embedding_name="bge_small",
    )
    request = _fake_request(module, bundle=bundle)
    payload = module.ClassifyRequest(
        text="What are your hours?",
        tenant_id="11111111-1111-1111-1111-111111111111",
    )

    response = asyncio.run(module.classify(payload, request, None))

    assert response.intent == "faq"
    assert response.intent in {"spam", "faq", "lead", "escalate", "ambiguous"}
    assert set(response.model_dump().keys()) == {"intent", "confidence"}


def test_low_confidence_returns_ambiguous():
    module = _load_module()
    bundle = FakeBundle(
        model=FakeModel([0.05, 0.79, 0.05, 0.05, 0.06]),
        internal_to_contract={
            "spam": "spam",
            "question": "faq",
            "lead": "lead",
            "escalate": "escalate",
            "unknown_or_agent": "ambiguous",
        },
        runtime_threshold=0.8,
        deployed_model="classical",
        embedding_name="bge_small",
    )
    request = _fake_request(module, bundle=bundle)
    payload = module.ClassifyRequest(
        text="I need some help",
        tenant_id="11111111-1111-1111-1111-111111111111",
    )

    response = asyncio.run(module.classify(payload, request, None))

    assert response.intent == "ambiguous"


def test_embed_without_token_returns_401():
    module = _load_module()
    request = _fake_request(module)
    request.headers = {}

    with pytest.raises(HTTPException) as exc_info:
        module._require_service_token(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "UNAUTHORIZED"


def test_embed_stub_returns_768_zero_floats():
    module = _load_module()
    request = _fake_request(module)
    payload = module.EmbedRequest(text="hello")

    response = asyncio.run(module.embed(payload, request, None))

    assert set(response.keys()) == {"embedding"}
    assert len(response["embedding"]) == 768
    assert all(value == 0.0 for value in response["embedding"])
