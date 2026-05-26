# Owner B
import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis

_KEY_PREFIX = "conversation"
_MAX_MESSAGES = 20
_TTL_SECONDS = 1800  # 30 minutes, refreshed on every write


def _key(tenant_id: uuid.UUID, session_id: str) -> str:
    return f"{_KEY_PREFIX}:{tenant_id}:{session_id}"


async def get_history(
    redis: aioredis.Redis,
    tenant_id: uuid.UUID,
    session_id: str,
) -> list[dict]:
    """Return up to 20 messages in chronological order (oldest first).

    LPUSH prepends new messages, so LRANGE 0 19 gives newest-first;
    we reverse so callers get a natural chronological list.
    """
    raw = await redis.lrange(_key(tenant_id, session_id), 0, _MAX_MESSAGES - 1)
    return [json.loads(item) for item in reversed(raw)]


async def append_message(
    redis: aioredis.Redis,
    tenant_id: uuid.UUID,
    session_id: str,
    *,
    role: str,
    content: str,
) -> None:
    """Prepend a message to the session list, trim to 20, and refresh the TTL.

    Only call this with guardrails-redacted content — never with raw PII.
    """
    message = json.dumps({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    key = _key(tenant_id, session_id)
    pipe = redis.pipeline()
    pipe.lpush(key, message)
    pipe.ltrim(key, 0, _MAX_MESSAGES - 1)
    pipe.expire(key, _TTL_SECONDS)
    await pipe.execute()
