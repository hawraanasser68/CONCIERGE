# Owner A (stub) — Owner B replaces this file entirely.
# Returns 501 so the app boots cleanly before B's implementation lands.

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/cms", tags=["cms"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def cms_stub(path: str):
    from fastapi import HTTPException
    raise HTTPException(status_code=501, detail="Not implemented — Owner B owns this route")
