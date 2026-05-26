# Owner A — backend/app/schemas/user.py
#
# Pydantic schemas for fastapi-users registration/login.
# UserRead / UserCreate / UserUpdate extend the fastapi-users base schemas
# so the library generates correct OpenAPI docs and validation.
#
# role and tenant_id are A's extensions to the base schema.
# The registration endpoint does NOT allow anyone to self-assign tenant_manager —
# that role is only assigned by provisioning scripts or migration seeds.

import uuid
from typing import Optional

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Shape returned by /api/v1/auth/me and embedded in JWT payloads."""
    role: str
    tenant_id: Optional[uuid.UUID] = None


class UserCreate(schemas.BaseUserCreate):
    """Body accepted by POST /api/v1/auth/register."""
    role: str = "tenant_admin"
    tenant_id: Optional[uuid.UUID] = None


class UserUpdate(schemas.BaseUserUpdate):
    """Body accepted by PATCH /api/v1/auth/users/{id} (fastapi-users user management)."""
    pass
