# Owner A — backend/app/repositories/tenant_costs_repo.py
#
# Upsert daily cost counters per tenant.
# Called by cost_meter.py — never called directly from routes.
# Uses ON CONFLICT (tenant_id, date) DO UPDATE so every call is idempotent.

import uuid
from datetime import date, timezone
from datetime import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TenantCostsRepository:

    async def increment(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        llm_tokens_in: int = 0,
        llm_tokens_out: int = 0,
        embed_tokens: int = 0,
        classify_calls: int = 0,
    ) -> None:
        """
        Upserts the row for (tenant_id, today) and adds the given deltas.
        All callers pass only the fields they touched — zeros are ignored via coalesce.
        """
        today = dt.now(timezone.utc).date()
        await session.execute(
            text("""
                INSERT INTO tenant_costs
                    (id, tenant_id, date, llm_tokens_in, llm_tokens_out, embed_tokens, classify_calls)
                VALUES
                    (gen_random_uuid(), :tid, :today, :tin, :tout, :embed, :classify)
                ON CONFLICT (tenant_id, date) DO UPDATE SET
                    llm_tokens_in  = tenant_costs.llm_tokens_in  + EXCLUDED.llm_tokens_in,
                    llm_tokens_out = tenant_costs.llm_tokens_out + EXCLUDED.llm_tokens_out,
                    embed_tokens   = tenant_costs.embed_tokens   + EXCLUDED.embed_tokens,
                    classify_calls = tenant_costs.classify_calls + EXCLUDED.classify_calls
            """),
            {
                "tid":      str(tenant_id),
                "today":    today,
                "tin":      llm_tokens_in,
                "tout":     llm_tokens_out,
                "embed":    embed_tokens,
                "classify": classify_calls,
            },
        )


tenant_costs_repo = TenantCostsRepository()
