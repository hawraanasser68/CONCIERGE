# Owner A — backend/app/models/__init__.py
#
# Imports every model so Alembic's env.py picks them all up during autogenerate.
# If you add a new model file, add its import here — otherwise the migration
# will not see the table and will generate a DROP TABLE in the next revision.

from app.models.agent_config import AgentConfig
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.chunk import Chunk
from app.models.cms import CmsPage
from app.models.escalation import Escalation
from app.models.lead import Lead
from app.models.tenant import Tenant
from app.models.tenant_costs import TenantCosts
from app.models.user import User
from app.models.widget import Widget

__all__ = [
    "Base",
    "Tenant",
    "User",
    "Widget",
    "AgentConfig",
    "CmsPage",
    "Chunk",
    "Lead",
    "Escalation",
    "AuditLog",
    "TenantCosts",
]
