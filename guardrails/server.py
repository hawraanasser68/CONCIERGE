# Owner C

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

import hvac
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


LOGGER = logging.getLogger("guardrails")
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.redaction import redact


class GuardrailsRequest(BaseModel):
    message: str
    tenant_id: UUID
    session_id: UUID
    direction: Literal["input", "output"]


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _read_service_token() -> str:
    vault_addr = os.getenv("VAULT_ADDR")
    vault_token = os.getenv("VAULT_TOKEN")
    if vault_addr and vault_token:
        client = hvac.Client(url=vault_addr, token=vault_token)
        if not client.is_authenticated():
            raise RuntimeError("Vault authentication failed — check VAULT_ADDR and VAULT_TOKEN")
        secret = client.secrets.kv.v2.read_secret_version(path="svc/guardrails")
        return secret["data"]["data"]["token"]

    fallback = os.getenv("GUARDRAILS_TOKEN")
    if fallback:
        LOGGER.warning("vault_unavailable_using_env_token_fallback")
        return fallback

    raise RuntimeError("Guardrails token unavailable — set VAULT_ADDR/VAULT_TOKEN or GUARDRAILS_TOKEN")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.service_token = _read_service_token()
    LOGGER.info("startup_complete")
    try:
        yield
    finally:
        LOGGER.info("shutdown_complete")


app = FastAPI(title="Concierge Guardrails Stub", lifespan=lifespan)


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


def _build_response(payload: GuardrailsRequest) -> dict[str, object]:
    redacted_message = redact(payload.message)
    flagged_categories = ["pii"] if redacted_message != payload.message else []
    LOGGER.info(
        "guardrails_check tenant_id=%s session_id=%s direction=%s allowed=true flagged_count=%d",
        payload.tenant_id,
        payload.session_id,
        payload.direction,
        len(flagged_categories),
    )
    return {
        "allowed": True,
        "flagged_categories": flagged_categories,
        "redacted_message": redacted_message,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/check/input")
async def check_input(
    payload: GuardrailsRequest,
    request: Request,
    _: None = Depends(_require_service_token),
) -> dict[str, object]:
    return _build_response(payload)


@app.post("/check/output")
async def check_output(
    payload: GuardrailsRequest,
    request: Request,
    _: None = Depends(_require_service_token),
) -> dict[str, object]:
    return _build_response(payload)
