# Owner A — backend/app/core/errors.py
#
# Shared exception types and HTTP error helpers used across the whole backend.
# Owner B uses ToolError when a tool call fails for a recoverable reason.

from fastapi import HTTPException


class ToolError(Exception):
    """Raised inside agent tools when the operation fails for a known reason.
    The agent catches this and returns a safe message to the visitor instead of crashing."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class GuardrailsUnavailableError(Exception):
    """Raised by guardrails_client when the sidecar is unreachable.
    The chat route catches this and returns HTTP 503 — never passes the message through."""
    pass


def not_found(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def forbidden(detail: str = "Forbidden") -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def conflict(detail: str = "Conflict") -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def bad_request(detail: str = "Bad request") -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def service_unavailable(detail: str = "Service unavailable") -> HTTPException:
    return HTTPException(status_code=503, detail=detail)
