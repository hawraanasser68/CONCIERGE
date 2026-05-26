# Owner A — backend/app/auth/widget_token.py
#
# Signs and verifies widget session JWTs.
# Owner D's token exchange endpoint calls sign_widget_jwt().
# Owner A's get_widget_session dependency calls verify_widget_jwt() on every chat request.
#
# JWT shape (frozen in INTERFACES.md):
#   { tenant_id, widget_id, origin, session_id, type="widget_session", iat, exp }
# Algorithm: HS256   TTL: 1 hour   Secret: from Vault at secret/widget/signing_key

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, Request

ALGORITHM = "HS256"
TTL_SECONDS = 3600          # 1 hour
CLOCK_SKEW_SECONDS = 30     # tolerance for minor clock drift between services
TOKEN_TYPE = "widget_session"


def sign_widget_jwt(
    *,
    signing_key: str,
    tenant_id: str,
    widget_id: str,
    origin: str,
    session_id: str,
) -> str:
    """
    Signs a widget session JWT. Called by Owner D's POST /api/v1/widget/token endpoint.
    signing_key is passed in (read from request.app.state by the caller).
    """
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "tenant_id": tenant_id,
        "widget_id": widget_id,
        "origin": origin,
        "session_id": session_id,
        "type": TOKEN_TYPE,
        "iat": now,
        "exp": now + TTL_SECONDS,
    }
    return jwt.encode(payload, signing_key, algorithm=ALGORITHM)


def verify_widget_jwt(token: str, signing_key: str) -> dict:
    """
    Decodes and validates a widget JWT. Returns the payload dict on success.
    Raises HTTPException on any validation failure.

    Validation order (from INTERFACES.md):
    1. Signature valid
    2. exp not passed (with clock skew tolerance)
    3. type == "widget_session"
    Returns payload — caller checks origin, widget_id, tenant status (steps 4-7).
    """
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[ALGORITHM],
            leeway=CLOCK_SKEW_SECONDS,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != TOKEN_TYPE:
        raise HTTPException(status_code=401, detail="Invalid token type")

    return payload
