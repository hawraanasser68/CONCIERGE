# Owner A (stub) — Owner B replaces this file entirely.
# Returns 501 so the app boots cleanly before B's implementation lands.

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/message")
async def send_message():
    from fastapi import HTTPException
    raise HTTPException(status_code=501, detail="Not implemented — Owner B owns this route")
