# Owner B — backend/app/tools/escalate.py
#
# The escalate agent tool. Inserts an Escalation row with status="open" and
# returns the ticket UUID. Maps conversation_id → session_id column — the LLM
# schema field name differs from the model column (see INTERFACES.md §5).
#
# tenant_id is injected server-side — absent from the LLM-facing input schema.

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.escalation_repo import escalation_repo


async def escalate(
    reason: str,
    conversation_id: str,           # LLM-facing name from INTERFACES.md schema
    tenant_id: uuid.UUID,           # injected from dependency — never from LLM args
    session: AsyncSession,
) -> dict:
    """Insert an escalation row and return the ticket ID.

    Column mapping: Escalation.session_id ← conversation_id (see INTERFACES.md).
    The LLM provides conversation_id; the model stores it as session_id.
    """
    reason = reason[:500]

    esc = await escalation_repo.insert(
        session,
        tenant_id,
        session_id=conversation_id,     # session_id column, NOT conversation_id
        reason=reason,
    )
    await session.flush()

    return {"escalated": True, "ticket_id": str(esc.id)}
