# Owner A — backend/app/schemas/lead.py
#
# Read-only response schema for GET /api/v1/admin/leads.
# Owner B writes the lead_repo.py and capture_lead tool that insert rows.
# This schema is only used by Owner A's admin route to serialise the response.

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LeadResponse(BaseModel):
    id: uuid.UUID
    session_id: str
    visitor_name: str
    contact: str
    intent: str
    classifier_score: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}
