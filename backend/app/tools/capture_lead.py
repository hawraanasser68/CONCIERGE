# Owner B — backend/app/tools/capture_lead.py
#
# The capture_lead agent tool. Validates contact as email OR E.164 phone number
# (spaces and hyphens are stripped before the E.164 check). Rate-limited to 5
# calls per session_id per hour. Writes Lead(visitor_name=name, ...) — the model
# column is visitor_name, not name (see INTERFACES.md §5).
#
# tenant_id and session_id are injected server-side — absent from the LLM-facing
# input schema so prompt injection cannot override tenant context or session scope.

import re
import uuid

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.lead_repo import lead_repo
from app.services.rate_limiter import check_rate_limit, increment_rate_limit

# Validation regexes (per INTERFACES.md)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
# E.164: + followed by 7–15 digits (spaces/hyphens stripped before check)
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def _is_valid_contact(contact: str) -> bool:
    cleaned = re.sub(r"[\s\-]", "", contact)
    return bool(_EMAIL_RE.match(contact)) or bool(_E164_RE.match(cleaned))


def _extract_contact(raw: str) -> str:
    """Pull just the email or E.164 phone out of a string that may include surrounding text.

    The LLM sometimes passes 'you can reach me at user@example.com' or
    'phone: +14155550177' instead of the bare value. This normalises it so
    validation doesn't reject an otherwise valid contact.
    """
    email_match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", raw)
    if email_match and _EMAIL_RE.match(email_match.group(0)):
        return email_match.group(0)
    phone_match = re.search(r"\+[1-9]\d{6,14}", re.sub(r"[\s\-]", "", raw))
    if phone_match:
        return phone_match.group(0)
    return raw


async def capture_lead(
    name: str,
    contact: str,
    intent: str,
    tenant_id: uuid.UUID,       # injected from dependency — never from LLM args
    session_id: str,            # from verified JWT
    session: AsyncSession,
    redis: aioredis.Redis,
    classifier_score: float | None = None,  # routed in by _lead_workflow for triage
) -> dict:
    """Validate, rate-limit, and persist a lead row.

    Column mapping: Lead.visitor_name ← name (not Lead.name — see INTERFACES.md).
    Rate limit: 5 capture_lead calls per session_id per hour.
    """
    name = name.strip()[:255]
    contact = contact.strip()[:255]
    intent = intent[:1000]

    if not name:
        return {"captured": False, "reason": "Name is required"}

    # Normalise: if the LLM included surrounding text (e.g. "reach me at user@example.com"),
    # extract just the email/phone so validation doesn't reject a valid contact.
    if not _is_valid_contact(contact):
        contact = _extract_contact(contact)

    if not _is_valid_contact(contact):
        return {
            "captured": False,
            "reason": "Contact must be a valid email or E.164 phone number (e.g. +14155550123)",
        }

    if not await check_rate_limit(redis, tenant_id, "capture_lead", session_id=session_id):
        return {"captured": False, "reason": "Too many lead capture attempts in this session"}

    lead = await lead_repo.insert(
        session,
        tenant_id,
        session_id=session_id,
        visitor_name=name,          # visitor_name column, NOT name
        contact=contact,
        intent=intent,
        classifier_score=classifier_score,
    )
    await session.flush()
    # MUST commit — get_session() does not auto-commit, so a bare flush leaves
    # the INSERT inside an open transaction that gets rolled back when the
    # request scope closes. Without this line, leads silently never persist.
    await session.commit()

    await increment_rate_limit(redis, tenant_id, "capture_lead", session_id=session_id)

    return {"lead_id": str(lead.id), "captured": True}
