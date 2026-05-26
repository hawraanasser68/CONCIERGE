# Owner A — backend/app/services/cost_meter.py
#
# Per-tenant cost attribution. Owner B calls these after every LLM/embed/classify call.
# Each function upserts the daily row in tenant_costs via the repo's ON CONFLICT clause.
#
# Owner B usage:
#   await record_llm_usage(session, tenant_id, tokens_in=450, tokens_out=120)
#   await record_embed_usage(session, tenant_id, tokens=512)
#   await record_classify_call(session, tenant_id)

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tenant_costs_repo import tenant_costs_repo


async def record_llm_usage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    tokens_in: int,
    tokens_out: int,
) -> None:
    """Call after every successful LLM completion. Pass the prompt and completion token counts."""
    await tenant_costs_repo.increment(
        session,
        tenant_id,
        llm_tokens_in=tokens_in,
        llm_tokens_out=tokens_out,
    )


async def record_embed_usage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    tokens: int,
) -> None:
    """Call after every embedding API call. Pass the total token count for the batch."""
    await tenant_costs_repo.increment(
        session,
        tenant_id,
        embed_tokens=tokens,
    )


async def record_classify_call(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> None:
    """Call after every POST /classify to the model server. Counts calls, not tokens."""
    await tenant_costs_repo.increment(
        session,
        tenant_id,
        classify_calls=1,
    )
