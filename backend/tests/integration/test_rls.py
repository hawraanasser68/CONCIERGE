# Owner A — backend/tests/integration/test_rls.py
#
# A-047 — Day 1 gate: Tenant A cannot see Tenant B rows under RLS.
#
# Strategy:
#   - Uses asyncpg (not SQLAlchemy ORM) for full control over the Postgres session.
#   - Creates a self-contained temp table with ENABLE + FORCE ROW LEVEL SECURITY.
#   - Creates a non-superuser role _rls_test_role and uses SET ROLE so that
#     FORCE RLS actually applies. (Superusers bypass RLS even with FORCE;
#     SET ROLE downgrades the privilege for the duration of the test.)
#   - Inserts rows for two tenants as the superuser (no RLS restriction on INSERT
#     when the connecting user bypasses RLS), then asserts cross-tenant isolation.
#   - Requires a live PostgreSQL connection. Skipped gracefully if unreachable.
#
# Run: TEST_DATABASE_URL=postgresql://concierge:<pw>@localhost:5432/concierge_test \
#        pytest tests/integration/test_rls.py -v

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="module")

try:
    import asyncpg  # type: ignore[import]
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

# Strip the SQLAlchemy driver prefix — asyncpg uses its own DSN format.
_RAW_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://concierge:concierge@localhost:5432/concierge_test",
).replace("postgresql+asyncpg://", "postgresql://")

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_TABLE = "_rls_test_isolation"
_ROLE  = "_rls_test_role"


# ── Module-scoped connection ───────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def pg():
    """Raw asyncpg connection; skips entire module if Postgres is unreachable."""
    if not ASYNCPG_AVAILABLE:
        pytest.skip("asyncpg not installed")

    try:
        conn = await asyncpg.connect(_RAW_URL)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unreachable — set TEST_DATABASE_URL to run RLS tests ({exc})")

    yield conn
    await conn.close()


@pytest.fixture(scope="module", autouse=True)
async def rls_setup(pg):
    """
    One-time setup: create the test table, enable RLS, create the non-superuser
    role, grant privileges, seed rows for two tenants.
    Torn down after all tests in the module complete.
    """
    await pg.execute(f"DROP TABLE IF EXISTS {_TABLE}")

    await pg.execute(f"""
        CREATE TABLE {_TABLE} (
            id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            name      TEXT NOT NULL
        )
    """)
    await pg.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    await pg.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    await pg.execute(f"""
        CREATE POLICY tenant_isolation ON {_TABLE}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::uuid)
    """)

    # Create the non-superuser role if it does not exist.
    await pg.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                CREATE ROLE {_ROLE};
            END IF;
        END
        $$
    """)
    await pg.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO {_ROLE}")

    # Seed rows as the superuser (superusers bypass RLS, so INSERT is unrestricted).
    await pg.execute(
        f"INSERT INTO {_TABLE} (tenant_id, name) VALUES ($1, $2), ($1, $3)",
        TENANT_A, "Widget A1", "Widget A2",
    )
    await pg.execute(
        f"INSERT INTO {_TABLE} (tenant_id, name) VALUES ($1, $2)",
        TENANT_B, "Widget B1",
    )

    yield

    await pg.execute(f"DROP TABLE IF EXISTS {_TABLE}")


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_tenant_a_sees_only_own_rows(pg):
    """With app.tenant_id = TENANT_A, only TENANT_A rows are returned."""
    async with pg.transaction():
        await pg.execute(f"SET LOCAL ROLE {_ROLE}")
        await pg.execute(
            "SELECT set_config('app.tenant_id', $1, TRUE)", str(TENANT_A)
        )
        rows = await pg.fetch(f"SELECT tenant_id FROM {_TABLE}")

    tenant_ids = {str(r["tenant_id"]) for r in rows}
    assert str(TENANT_A) in tenant_ids, "Expected Tenant A rows to be visible"
    assert str(TENANT_B) not in tenant_ids, (
        "RLS breach: Tenant A context returned Tenant B rows"
    )
    assert len(rows) == 2, f"Expected 2 rows for Tenant A, got {len(rows)}"


async def test_tenant_b_sees_only_own_rows(pg):
    """With app.tenant_id = TENANT_B, only TENANT_B rows are returned."""
    async with pg.transaction():
        await pg.execute(f"SET LOCAL ROLE {_ROLE}")
        await pg.execute(
            "SELECT set_config('app.tenant_id', $1, TRUE)", str(TENANT_B)
        )
        rows = await pg.fetch(f"SELECT tenant_id FROM {_TABLE}")

    tenant_ids = {str(r["tenant_id"]) for r in rows}
    assert str(TENANT_B) in tenant_ids, "Expected Tenant B rows to be visible"
    assert str(TENANT_A) not in tenant_ids, (
        "RLS breach: Tenant B context returned Tenant A rows"
    )
    assert len(rows) == 1, f"Expected 1 row for Tenant B, got {len(rows)}"


async def test_missing_tenant_context_returns_no_rows(pg):
    """
    With no app.tenant_id set, current_setting(..., TRUE) returns NULL.
    NULL = NULL is UNKNOWN in SQL, so no rows pass the policy.
    A bug that forgets to call set_tenant_rls() results in empty reads, not a data leak.
    """
    async with pg.transaction():
        await pg.execute(f"SET LOCAL ROLE {_ROLE}")
        await pg.execute("SELECT set_config('app.tenant_id', '', TRUE)")
        rows = await pg.fetch(f"SELECT tenant_id FROM {_TABLE}")

    assert len(rows) == 0, (
        f"Expected 0 rows with no tenant context, got {len(rows)} — RLS policy is broken"
    )
