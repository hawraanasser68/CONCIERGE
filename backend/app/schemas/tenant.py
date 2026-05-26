# Owner A — backend/app/schemas/tenant.py
#
# Request/response schemas for tenant provisioning at /api/v1/platform/tenants.
# Only tenant_manager role reaches these endpoints.

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class TenantCreate(BaseModel):
    """Body for POST /api/v1/platform/tenants."""
    slug: str
    name: str
    first_admin_email: EmailStr


class TenantCreateResponse(BaseModel):
    """
    Returned to the manager after a tenant is provisioned.
    invite_token is a one-time UUID the manager forwards to the first admin.
    The admin presents it at POST /api/v1/auth/register to self-register.
    """
    tenant_id: uuid.UUID
    invite_token: str


class TenantResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    created_at: datetime
    erased_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
