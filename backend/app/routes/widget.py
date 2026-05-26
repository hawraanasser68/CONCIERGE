# Owner A (stub) — Owner D replaces this file entirely.
# Returns 501 so the app boots cleanly before D's implementation lands.

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/widget", tags=["widget"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def widget_stub(path: str):
    from fastapi import HTTPException
    raise HTTPException(status_code=501, detail="Not implemented — Owner D owns this route")
