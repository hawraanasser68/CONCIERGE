# Owner A — backend/app/auth/service_token.py
#
# Validates Bearer tokens on inbound calls from internal services.
# Owner C's guardrails sidecar calls the backend's agent-config endpoint
# using a service token from Vault. This dependency validates that token.

import structlog
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = structlog.get_logger()
_bearer = HTTPBearer(auto_error=False)


async def verify_service_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    """
    FastAPI dependency for internal service-to-service endpoints.
    Validates that the Bearer token matches the one seeded in Vault.
    Returns None on success — raises 401 on failure.

    Usage:
        @router.get("/internal/agent-config")
        async def get_agent_config(_: None = Depends(verify_service_token)):
            ...
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing service token")

    # The expected token is the guardrails service token stored in app.state
    expected = getattr(request.app.state, "guardrails_token", None)
    if not expected or credentials.credentials != expected:
        # Do not log the received token — only log that auth failed
        log.warning("service_token_invalid", path=str(request.url.path))
        raise HTTPException(status_code=401, detail="Invalid service token")
