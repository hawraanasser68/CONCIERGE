# Owner A — backend/app/auth/roles.py
#
# Three-role model for the platform.
# Use require_role() as a FastAPI dependency on any route that needs role enforcement.

from enum import Enum

from fastapi import Depends, HTTPException

# Safe top-level import: auth/users.py does not import from roles.py
from app.auth.users import fastapi_users
from app.models.user import User


class Role(str, Enum):
    tenant_manager = "tenant_manager"
    tenant_admin = "tenant_admin"
    member = "member"


# Reusable dependency — returns the authenticated active user
_current_user_dep = fastapi_users.current_user(active=True)


def require_role(*roles: Role):
    """
    FastAPI dependency factory that enforces role checks.

    Usage:
        @router.get("/admin/widgets")
        async def list_widgets(user: User = Depends(require_role(Role.tenant_admin))):
            ...
    """
    async def _check(current_user: User = Depends(_current_user_dep)) -> User:
        if current_user.role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user.role}' is not allowed here.",
            )
        return current_user

    return _check
