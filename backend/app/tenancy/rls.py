# Owner A — backend/app/tenancy/rls.py
#
# Sets the Postgres session variable that drives Row-Level Security.
# Called inside get_current_tenant_id() (in dependencies.py) on every request.
# The TRUE flag makes it transaction-scoped — resets automatically at transaction end.
# Safe for connection pooling: no explicit reset needed.

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Sentinel UUID for tenant_manager requests — matches no real tenant row.
# RLS blocks all content tables safely for managers without special-casing each table.
MANAGER_SENTINEL = "00000000-0000-0000-0000-000000000000"


async def set_tenant_rls(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """
    Sets app.tenant_id as a transaction-scoped Postgres session variable.
    RLS policies read this via current_setting('app.tenant_id', TRUE).
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, TRUE)"),
        {"tid": str(tenant_id)},
    )


async def set_manager_rls(session: AsyncSession) -> None:
    """
    Sets the sentinel UUID for tenant_manager requests.
    The sentinel matches no real tenant_id — RLS blocks all tenant-scoped tables.
    Managers access data only through explicit queries in manager routes (no RLS bypass).
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, TRUE)"),
        {"tid": MANAGER_SENTINEL},
    )
