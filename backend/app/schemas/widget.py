# Owner A — backend/app/schemas/widget.py
#
# Request/response schemas for the widget CRUD endpoints at /api/v1/admin/widgets.
# Owner D's admin UI and the token exchange endpoint consume these shapes.

import uuid
from typing import List, Optional

from pydantic import BaseModel


class WidgetCreate(BaseModel):
    name: str
    allowed_origins: List[str] = []
    greeting: str = "Hi! How can I help you today?"
    persona_name: str = "Assistant"


class WidgetUpdate(BaseModel):
    """All fields optional — supports partial updates."""
    name: Optional[str] = None
    allowed_origins: Optional[List[str]] = None
    greeting: Optional[str] = None
    persona_name: Optional[str] = None


class WidgetResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    allowed_origins: List[str]
    greeting: str
    persona_name: str
    is_active: bool

    model_config = {"from_attributes": True}
