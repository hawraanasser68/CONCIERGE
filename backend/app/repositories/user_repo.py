# Owner A — backend/app/repositories/user_repo.py
#
# User lookup helpers. Not a TenantRepository subclass because the users table
# uses ENABLE (not FORCE) RLS — lookups by email happen before tenant context is set.
# All callers must enforce role checks at the route level via require_role().

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:

    async def get_by_id(self, session: AsyncSession, user_id: uuid.UUID) -> User | None:
        return await session.get(User, user_id)

    async def get_by_email(self, session: AsyncSession, email: str) -> User | None:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> list[User]:
        result = await session.execute(
            select(User).where(User.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def create(
        self,
        session: AsyncSession,
        *,
        email: str,
        hashed_password: str,
        role: str,
        tenant_id: uuid.UUID | None = None,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            role=role,
            tenant_id=tenant_id,
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.flush()
        return user


user_repo = UserRepository()
