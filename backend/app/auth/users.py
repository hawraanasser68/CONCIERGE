# Owner A — backend/app/auth/users.py
#
# fastapi-users configuration — handles login, registration, and JWT issuance.
# The JWT secret is read from app.state (loaded from Vault at startup).

import uuid
from typing import Optional

import structlog
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase

from app.models.user import User

log = structlog.get_logger()

ACCESS_TOKEN_LIFETIME = 60 * 60 * 24  # 24 hours for admin JWT (widget tokens are 1h)


async def get_user_db(request: Request):
    """
    Yields the SQLAlchemy user database adapter.
    Uses request.app.state.session_factory directly — avoids circular import
    with dependencies.py which also needs fastapi_users from this module.
    """
    async with request.app.state.session_factory() as session:
        yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def on_after_register(self, user: User, request: Optional[Request] = None):
        log.info("user_registered", user_id=str(user.id), email=user.email)

    async def on_after_login(self, user: User, request: Optional[Request] = None, response=None):
        log.info("user_login", user_id=str(user.id), role=user.role)


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


def get_jwt_strategy(request: Request) -> JWTStrategy:
    """Reads the signing key from app.state — set at startup from Vault."""
    return JWTStrategy(
        secret=request.app.state.widget_signing_key,
        lifetime_seconds=ACCESS_TOKEN_LIFETIME,
    )


bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/login")

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
