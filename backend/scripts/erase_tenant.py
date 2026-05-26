# Owner A — backend/scripts/erase_tenant.py
#
# CLI wrapper for the GDPR/CCPA right-to-erasure flow.
# Calls the same tenancy.manager.erase_tenant() used by the API endpoint,
# so the erasure logic is tested in one place.
#
# Usage:
#   DATABASE_URL=postgresql+asyncpg://... \
#   REDIS_URL=redis://localhost:6379/0 \
#     python scripts/erase_tenant.py <tenant_id> [--actor-id <uuid>]
#
# --actor-id defaults to the platform sentinel UUID if not provided.
# Always run this with a DB backup handy — erasure is irreversible.

import argparse
import asyncio
import os
import uuid

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.tenancy.manager import erase_tenant

DATABASE_URL = os.environ.get("DATABASE_URL")
REDIS_URL    = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Sentinel actor_id used when the erasure is triggered by an automated process
# rather than a named human operator.
PLATFORM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def run(tenant_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL env var is required")

    engine  = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis   = await aioredis.from_url(REDIS_URL, decode_responses=True)

    print(f"Erasing tenant {tenant_id} (actor: {actor_id}) ...")

    async with factory() as session:
        await erase_tenant(session, redis, tenant_id=tenant_id, actor_id=actor_id)

    await redis.aclose()
    await engine.dispose()
    print("Erasure complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="GDPR tenant erasure CLI")
    parser.add_argument("tenant_id", type=uuid.UUID, help="UUID of the tenant to erase")
    parser.add_argument(
        "--actor-id",
        type=uuid.UUID,
        default=PLATFORM_ACTOR,
        help="UUID of the operator triggering the erasure (written to audit_log)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.tenant_id, args.actor_id))


if __name__ == "__main__":
    main()
