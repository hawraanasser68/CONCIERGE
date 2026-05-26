# Owner A — backend/app/routes/auth.py
#
# Mounts the fastapi-users login and registration endpoints under /api/v1/auth.
# Auto-discovered by main.py via the `router` variable.
#
# Exposed endpoints:
#   POST /api/v1/auth/login   → returns Bearer JWT
#   POST /api/v1/auth/logout  → invalidates session (no-op for stateless JWT)
#   POST /api/v1/auth/register → creates a new user account

from fastapi import APIRouter

from app.auth.users import auth_backend, fastapi_users
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Login and logout — Bearer JWT transport
router.include_router(fastapi_users.get_auth_router(auth_backend))

# Registration — open for dev; production gates this behind invite-token validation
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate)
)
