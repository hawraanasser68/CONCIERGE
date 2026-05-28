# Owner C

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import hvac
import joblib
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator


LOGGER = logging.getLogger("modelserver")
BASE_DIR = Path(__file__).resolve().parent
MODEL_CARD_PATH = BASE_DIR / "model_card.yaml"
THRESHOLD_CONFIG_PATH = BASE_DIR / "artifacts" / "threshold.json"
LABEL_MAPPING_PATH = BASE_DIR / "artifacts" / "label_mapping.json"
DEFAULT_EMBEDDING_DIM = 768
OPENAI_EMBED_MODEL = "text-embedding-3-small"


@dataclass
class LoadedClassifier:
    model: Any
    internal_to_contract: dict[str, str]
    runtime_threshold: float
    deployed_model: str
    embedding_name: str


@dataclass
class EmbeddingProvider:
    client: Any
    model: str
    dimensions: int

    def embed_one(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
        )
        return list(response.data[0].embedding)


class ClassifyRequest(BaseModel):
    text: str = Field(..., max_length=4000, description="Raw visitor message")
    tenant_id: UUID

    @model_validator(mode="after")
    def validate_text(self) -> "ClassifyRequest":
        if not self.text.strip():
            raise ValueError("text must be non-empty")
        return self


class ClassifyResponse(BaseModel):
    intent: str
    confidence: float


class EmbedRequest(BaseModel):
    text: str | None = None
    texts: list[str] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "EmbedRequest":
        has_text = self.text is not None and self.text.strip() != ""
        has_texts = self.texts is not None and len(self.texts) > 0
        if has_text == has_texts:
            raise ValueError("provide exactly one of text or texts")
        if self.texts is not None and any(not item.strip() for item in self.texts):
            raise ValueError("texts entries must be non-empty")
        return self


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected mapping in {path}")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected object in {path}")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_artifact(path_value: str) -> Path:
    return BASE_DIR / path_value


def _read_service_token() -> str:
    vault_addr = os.getenv("VAULT_ADDR")
    vault_token = os.getenv("VAULT_TOKEN")
    if vault_addr and vault_token:
        client = hvac.Client(url=vault_addr, token=vault_token)
        if not client.is_authenticated():
            raise RuntimeError("Vault authentication failed — check VAULT_ADDR and VAULT_TOKEN")
        secret = client.secrets.kv.v2.read_secret_version(path="svc/modelserver")
        return secret["data"]["data"]["token"]

    fallback = os.getenv("MODELSERVER_TOKEN")
    if fallback:
        LOGGER.warning("vault_unavailable_using_env_token_fallback")
        return fallback

    raise RuntimeError("Modelserver token unavailable — set VAULT_ADDR/VAULT_TOKEN or MODELSERVER_TOKEN")


def _read_openai_api_key() -> str | None:
    vault_addr = os.getenv("VAULT_ADDR")
    vault_token = os.getenv("VAULT_TOKEN")
    if vault_addr and vault_token:
        try:
            client = hvac.Client(url=vault_addr, token=vault_token)
            if client.is_authenticated():
                secret = client.secrets.kv.v2.read_secret_version(path="embed/api_key")
                key = secret["data"]["data"].get("key", "")
                if key:
                    return key
        except Exception as exc:
            LOGGER.warning("vault_embed_key_read_failed error=%s", exc)

    return os.getenv("OPENAI_API_KEY") or None


def _load_embedding_provider() -> EmbeddingProvider | None:
    api_key = _read_openai_api_key()
    if not api_key:
        LOGGER.warning("openai_api_key_unavailable embedder=disabled")
        return None
    try:
        from openai import OpenAI
    except ImportError:
        LOGGER.warning("openai_sdk_unavailable embedder=disabled")
        return None
    client = OpenAI(api_key=api_key)
    return EmbeddingProvider(
        client=client,
        model=OPENAI_EMBED_MODEL,
        dimensions=DEFAULT_EMBEDDING_DIM,
    )


def _load_classifier_bundle() -> LoadedClassifier:
    model_card = _load_yaml(MODEL_CARD_PATH)
    classifier_card = model_card["classifier"]
    deployed_model = classifier_card["deployed_model"]
    if deployed_model != "classical":
        raise RuntimeError(f"Unsupported deployed_model for current runtime: {deployed_model}")

    artifact_path = _resolve_artifact(classifier_card["artifact_path"])
    expected_hash = classifier_card["artifact_sha256"]
    actual_hash = _sha256_file(artifact_path)
    if actual_hash != expected_hash:
        LOGGER.critical(
            "FATAL: artifact hash mismatch — expected %s, got %s",
            expected_hash,
            actual_hash,
        )
        raise SystemExit(1)

    threshold_config = _load_json(THRESHOLD_CONFIG_PATH)
    runtime_threshold = float(threshold_config["runtime_serving_threshold"])

    label_mapping = _load_json(LABEL_MAPPING_PATH)
    internal_to_contract = label_mapping["internal_to_contract"]

    model = joblib.load(artifact_path)
    embedding_card = model_card.get("embedding", {})
    embedding_name = embedding_card.get("model", "openai_text_embedding_3_small")
    return LoadedClassifier(
        model=model,
        internal_to_contract=internal_to_contract,
        runtime_threshold=runtime_threshold,
        deployed_model=deployed_model,
        embedding_name=embedding_name,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        app.state.service_token = _read_service_token()
        app.state.classifier_bundle = _load_classifier_bundle()
        app.state.embedding_provider = _load_embedding_provider()
        embedder_status = "openai" if app.state.embedding_provider else "disabled"
        LOGGER.info(
            "startup_complete classifier=%s runtime_threshold=%.2f embedder=%s",
            app.state.classifier_bundle.deployed_model,
            app.state.classifier_bundle.runtime_threshold,
            embedder_status,
        )
        yield
    finally:
        LOGGER.info("shutdown_complete")


app = FastAPI(title="Concierge Model Server", lifespan=lifespan)


def _error_response(status_code: int, error: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "code": code})


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(422, str(exc), "INVALID_INPUT")


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and {"error", "code"} <= set(exc.detail):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    code = "UNAUTHORIZED" if exc.status_code == 401 else "INVALID_INPUT"
    return _error_response(exc.status_code, str(exc.detail), code)


def _require_service_token(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "")
    expected = request.app.state.service_token
    if not auth_header.startswith("Bearer ") or auth_header[7:] != expected:
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing or invalid service token", "code": "UNAUTHORIZED"},
        )


def _get_bundle(request: Request) -> LoadedClassifier:
    bundle = getattr(request.app.state, "classifier_bundle", None)
    if bundle is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Model artifact not loaded", "code": "MODEL_NOT_LOADED"},
        )
    return bundle


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    bundle = getattr(request.app.state, "classifier_bundle", None)
    classifier = bundle.deployed_model if bundle is not None else "unloaded"
    embedding = bundle.embedding_name if bundle is not None else "stub"
    return {"status": "ok", "classifier": classifier, "embedding": embedding}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(
    payload: ClassifyRequest,
    request: Request,
    _: None = Depends(_require_service_token),
) -> ClassifyResponse:
    bundle = _get_bundle(request)
    start = time.perf_counter()

    probabilities = bundle.model.predict_proba([payload.text])[0]
    labels = list(bundle.model.classes_)
    best_index = max(range(len(probabilities)), key=lambda idx: float(probabilities[idx]))
    internal_label = str(labels[best_index])
    confidence = float(probabilities[best_index])
    mapped_label = bundle.internal_to_contract.get(internal_label)
    if mapped_label is None:
        raise HTTPException(
            status_code=503,
            detail={"error": f"Unknown classifier label: {internal_label}", "code": "MODEL_NOT_LOADED"},
        )

    intent = mapped_label if confidence >= bundle.runtime_threshold else "ambiguous"
    latency_ms = (time.perf_counter() - start) * 1000
    LOGGER.info(
        "classification tenant_id=%s intent=%s confidence=%.6f latency_ms=%.3f",
        payload.tenant_id,
        intent,
        confidence,
        latency_ms,
    )
    return ClassifyResponse(intent=intent, confidence=confidence)


@app.post("/embed")
async def embed(
    payload: EmbedRequest,
    request: Request,
    _: None = Depends(_require_service_token),
) -> dict[str, list[float] | list[list[float]]]:
    _get_bundle(request)
    provider: EmbeddingProvider | None = getattr(request.app.state, "embedding_provider", None)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Embedding provider not configured", "code": "EMBEDDER_UNAVAILABLE"},
        )

    start = time.perf_counter()
    try:
        if payload.text is not None:
            vector = provider.embed_one(payload.text)
            latency_ms = (time.perf_counter() - start) * 1000
            LOGGER.info(
                "embed model=%s dim=%d latency_ms=%.3f",
                provider.model,
                len(vector),
                latency_ms,
            )
            return {"embedding": vector}

        assert payload.texts is not None
        vectors = [provider.embed_one(text) for text in payload.texts]
        latency_ms = (time.perf_counter() - start) * 1000
        LOGGER.info(
            "embed_batch model=%s count=%d dim=%d latency_ms=%.3f",
            provider.model,
            len(vectors),
            len(vectors[0]) if vectors else 0,
            latency_ms,
        )
        return {"embeddings": vectors}
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.error("embed_failed error=%s", exc)
        raise HTTPException(
            status_code=502,
            detail={"error": "Embedding provider request failed", "code": "EMBEDDER_UPSTREAM_ERROR"},
        )
