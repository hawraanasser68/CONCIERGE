# Owner A — backend/scripts/seed_dev_data.py
#
# Idempotent dev seed. Safe to run multiple times — skips rows that already exist.
# The migration seeds these rows too, but this script lets you re-seed after a wipe
# without re-running migrations.
#
# Usage:
#   DATABASE_URL=postgresql+asyncpg://concierge:password@localhost:5432/concierge \
#     python scripts/seed_dev_data.py

import asyncio
import os
import uuid

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.agent_config import AgentConfig
from app.models.tenant import Tenant
from app.models.user import User
from app.models.widget import Widget

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL env var is required")

TENANT_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

DEV_HASH = bcrypt.hashpw(b"devpassword", bcrypt.gensalt(12)).decode()

TENANTS = [
    {"id": TENANT_A_ID, "slug": "bloom-florista", "name": "Bloom Florista"},
    {"id": TENANT_B_ID, "slug": "acme-plumbing",  "name": "ACME Plumbing"},
]

USERS = [
    {
        "email": "admin@bloom-florista.test",
        "role": "tenant_admin",
        "tenant_id": TENANT_A_ID,
    },
    {
        "email": "admin@acme-plumbing.test",
        "role": "tenant_admin",
        "tenant_id": TENANT_B_ID,
    },
    {
        "email": "platform@concierge.test",
        "role": "tenant_manager",
        "tenant_id": None,
    },
]

WIDGETS = [
    {
        "tenant_id": TENANT_A_ID,
        "name": "Bloom Florista Chat",
        "greeting": "Hi! Welcome to Bloom Florista. How can I help you today?",
        "persona_name": "Flora",
        "allowed_origins": ["http://localhost:3000"],
    },
    {
        "tenant_id": TENANT_B_ID,
        "name": "ACME Plumbing Chat",
        "greeting": "Hi! Welcome to ACME Plumbing. How can I help you today?",
        "persona_name": "Max",
        "allowed_origins": ["http://localhost:3000"],
    },
]


async def seed(session: AsyncSession) -> None:
    # Tenants
    for t in TENANTS:
        existing = await session.get(Tenant, t["id"])
        if existing:
            print(f"  skip tenant {t['slug']} (already exists)")
            continue
        session.add(Tenant(id=t["id"], slug=t["slug"], name=t["name"]))
        print(f"  created tenant {t['slug']}")

    await session.flush()

    # Agent config (one per tenant)
    for tenant_id in [TENANT_A_ID, TENANT_B_ID]:
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.tenant_id == tenant_id)
        )
        if result.scalar_one_or_none():
            print(f"  skip agent_config for {tenant_id} (already exists)")
            continue
        session.add(AgentConfig(tenant_id=tenant_id))
        print(f"  created agent_config for {tenant_id}")

    await session.flush()

    # Users
    for u in USERS:
        result = await session.execute(select(User).where(User.email == u["email"]))
        if result.scalar_one_or_none():
            print(f"  skip user {u['email']} (already exists)")
            continue
        session.add(User(
            email=u["email"],
            hashed_password=DEV_HASH,
            role=u["role"],
            tenant_id=u["tenant_id"],
            is_active=True,
            is_superuser=False,
            is_verified=False,
        ))
        print(f"  created user {u['email']}")

    await session.flush()

    # Widgets
    for w in WIDGETS:
        result = await session.execute(
            select(Widget).where(
                Widget.tenant_id == w["tenant_id"],
                Widget.name == w["name"],
            )
        )
        if result.scalar_one_or_none():
            print(f"  skip widget '{w['name']}' (already exists)")
            continue
        session.add(Widget(**w))
        print(f"  created widget '{w['name']}'")

    await session.commit()
    print("done.")


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
