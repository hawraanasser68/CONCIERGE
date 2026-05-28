# Owner A — backend/app/services/rate_limiter.py
#
# Per-tenant Redis rate limiting. Owner B calls these two functions on every action.
#
# Limits from the spec:
#   chat          60 / hour  — scoped to session_id
#   capture_lead   5 / hour  — scoped to session_id
#   llm_call    1000 / day   — scoped to tenant
#   embed       2000 / day   — scoped to tenant
#   classify    5000 / day   — scoped to tenant
#
# Redis key: ratelimit:{tenant_id}:{action}:{window_epoch}
# The window epoch is the floor of (now / window_seconds), so the key changes
# automatically when the window rolls over — no explicit expiry deletion needed.
# TTL is set to 2× the window so Redis cleans up stale keys without manual work.

import time
import uuid

import redis.asyncio as aioredis

# (limit, window_seconds, scope)
# scope="session" → key includes session_id; scope="tenant" → tenant-only
_LIMITS: dict[str, tuple[int, int, str]] = {
    "chat":          (60,   3600,  "session"),
    "capture_lead":  (5,    3600,  "session"),
    "llm_call":      (1000, 86400, "tenant"),
    "embed":         (2000, 86400, "tenant"),
    "classify":      (5000, 86400, "tenant"),
}


def _key(
    tenant_id: uuid.UUID, action: str, session_id: str | None, window_seconds: int, scope: str
) -> str:
    epoch = int(time.time()) // window_seconds
    if scope == "session":
        return f"ratelimit:{tenant_id}:{action}:{session_id}:{epoch}"
    return f"ratelimit:{tenant_id}:{action}:{epoch}"


async def check_rate_limit(
    redis: aioredis.Redis,
    tenant_id: uuid.UUID,
    action: str,
    session_id: str | None = None,
) -> bool:
    """
    Returns True if the action is within its limit, False if the limit is exceeded.
    Call this BEFORE executing the action. Does NOT increment the counter.

    Owner B usage:
        if not await check_rate_limit(redis, tenant_id, "chat", session_id=session_id):
            raise HTTPException(429, "Rate limit exceeded")
    """
    if action not in _LIMITS:
        return True  # unknown actions are not rate-limited

    limit, window_seconds, scope = _LIMITS[action]
    key = _key(tenant_id, action, session_id, window_seconds, scope)

    count = await redis.get(key)
    if count is None:
        return True
    return int(count) < limit


async def increment_rate_limit(
    redis: aioredis.Redis,
    tenant_id: uuid.UUID,
    action: str,
    session_id: str | None = None,
) -> None:
    """
    Increments the counter for this action. Call this AFTER the action succeeds.
    Sets TTL to 2× the window so Redis auto-cleans stale keys.

    Owner B usage:
        await increment_rate_limit(redis, tenant_id, "chat", session_id=session_id)
    """
    if action not in _LIMITS:
        return

    limit, window_seconds, scope = _LIMITS[action]
    key = _key(tenant_id, action, session_id, window_seconds, scope)

    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds * 2)
    await pipe.execute()
