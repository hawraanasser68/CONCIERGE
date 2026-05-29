# Owner A — backend/migrations/versions/0001_initial_schema.py
#
# THE single initial migration. Creates every table, enables RLS, creates indexes,
# and seeds the two demo tenants + platform manager.
#
# RULES:
# - Only Owner A generates migration files. Other owners define models; A runs autogenerate.
# - Never edit this file after it has been applied. Create a new migration instead.
# - Downgrade drops everything — only safe in dev. Never run downgrade in production.

"""Initial schema — all tables, RLS policies, IVFFlat index, seed data

Revision ID: 0001
Revises:
Create Date: 2026-05-26
"""

import uuid

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# ── Seed constants ─────────────────────────────────────────────────────────────

# Fixed UUIDs — hardcoded across all eval fixtures and red-team probes. Never change.
TENANT_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

# Dev-only seed password. Change via the admin UI before any real use.
# Using bcrypt directly — passlib 1.7.4 relies on bcrypt.__about__ which was
# removed in bcrypt 4.0, causing a crash when bcrypt 5.x is installed.
_DEV_HASH = bcrypt.hashpw(b"devpassword", bcrypt.gensalt(12)).decode()

# ── Tables with RLS ─────────────────────────────────────────────────────────────

# These tables are isolated per tenant using the app.tenant_id session variable.
# widgets, agent_config, cms_pages, chunks, leads, escalations, tenant_costs
# get ENABLE + FORCE — the DB owner is also subject to RLS on these.
#
# users gets ENABLE only (not FORCE) — the DB owner bypasses RLS.
# Reason: fastapi-users queries users by email during login, before any tenant
# context is established. Forcing RLS would make login impossible.
# Tenant isolation on users is enforced at the route level via get_current_user.

RLS_FORCE_TABLES = [
    "widgets",
    "agent_config",
    "cms_pages",
    "chunks",
    "leads",
    "escalations",
    "tenant_costs",
]


def upgrade() -> None:
    conn = op.get_bind()

    # ── pgvector extension ──────────────────────────────────────────────────────
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    # ── tenants ─────────────────────────────────────────────────────────────────
    # Root entity — no tenant_id FK, no RLS. Role-level access only.
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("slug", sa.String(), unique=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'erasing', 'erased')",
            name="tenants_status_check",
        ),
    )

    # ── users ───────────────────────────────────────────────────────────────────
    # fastapi-users base columns + role + tenant_id.
    # tenant_id is NULL for tenant_manager role.
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("email", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('tenant_manager', 'tenant_admin', 'member')",
            name="users_role_check",
        ),
    )
    # ENABLE but not FORCE — see note at top of file
    conn.execute(sa.text("ALTER TABLE users ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text(
        "CREATE POLICY tenant_isolation ON users "
        "USING (tenant_id = current_setting('app.tenant_id', TRUE)::uuid "
        "OR tenant_id IS NULL)"
    ))

    # ── widgets ─────────────────────────────────────────────────────────────────
    op.create_table(
        "widgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "allowed_origins",
            ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "greeting",
            sa.Text(),
            nullable=False,
            server_default="Hi! How can I help you today?",
        ),
        sa.Column(
            "persona_name", sa.String(), nullable=False, server_default="Assistant"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── agent_config ─────────────────────────────────────────────────────────────
    op.create_table(
        "agent_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "persona_name", sa.String(), nullable=False, server_default="Assistant"
        ),
        sa.Column("persona_description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "enabled_tools",
            ARRAY(sa.String()),
            nullable=False,
            server_default="{rag_search,capture_lead,escalate}",
        ),
        sa.Column(
            "blocked_topics", ARRAY(sa.String()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "allowed_topics", ARRAY(sa.String()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "max_tool_iterations", sa.Integer(), nullable=False, server_default="5"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", name="agent_config_tenant_id_key"),
    )

    # ── cms_pages ────────────────────────────────────────────────────────────────
    op.create_table(
        "cms_pages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "is_published", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="cms_pages_tenant_slug_key"),
    )

    # ── chunks ────────────────────────────────────────────────────────────────────
    # Embedding column is vector(768) — added via raw SQL because Alembic's
    # Column() cannot express the pgvector type natively.
    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cms_pages.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Add vector column separately — pgvector type not expressible via sa.Column()
    conn.execute(sa.text("ALTER TABLE chunks ADD COLUMN embedding vector(768)"))

    # IVFFlat index for approximate nearest-neighbour search.
    # lists=100 is a good default for up to ~1M vectors; tune upward as data grows.
    # The tenant_id index is mandatory — without it, ANN queries do a full table scan.
    conn.execute(sa.text(
        "CREATE INDEX chunks_embedding_ivfflat_idx "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    ))

    # ── leads ─────────────────────────────────────────────────────────────────────
    op.create_table(
        "leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("session_id", sa.String(), nullable=False, index=True),
        sa.Column("visitor_name", sa.String(), nullable=False),
        sa.Column("contact", sa.String(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("classifier_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── escalations ───────────────────────────────────────────────────────────────
    op.create_table(
        "escalations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("session_id", sa.String(), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'closed')",
            name="escalations_status_check",
        ),
    )

    # ── audit_log ─────────────────────────────────────────────────────────────────
    # No RLS. Append-only. tenant_manager reads via route check. Never deleted.
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False, index=True),
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── tenant_costs ──────────────────────────────────────────────────────────────
    op.create_table(
        "tenant_costs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("llm_tokens_in", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "llm_tokens_out", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("embed_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "classify_calls", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "date", name="tenant_costs_tenant_date_key"),
    )

    # ── RLS: ENABLE + FORCE on the 7 content tables ───────────────────────────────
    for table in RLS_FORCE_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', TRUE)::uuid)"
        ))

    # ── Seed data ──────────────────────────────────────────────────────────────────
    # These exact UUIDs are referenced in all eval fixtures and red-team probes.
    # Dev password for all seed users: "devpassword" — change via admin UI before demo.

    # Before inserting into RLS-protected tables, set the session variable so the
    # policy allows the insert. We use each tenant's own UUID for their rows.
    conn.execute(sa.text(
        f"SELECT set_config('app.tenant_id', '{TENANT_A_ID}', TRUE)"
    ))

    conn.execute(sa.text(f"""
        INSERT INTO tenants (id, slug, name, status)
        VALUES ('{TENANT_A_ID}', 'bloom-florista', 'Bloom Florista', 'active')
    """))

    conn.execute(sa.text(f"""
        INSERT INTO tenants (id, slug, name, status)
        VALUES ('{TENANT_B_ID}', 'acme-plumbing', 'ACME Plumbing', 'active')
    """))

    # Seed admin user for Tenant A
    conn.execute(sa.text(f"""
        INSERT INTO users (id, tenant_id, email, hashed_password, role, is_active, is_superuser, is_verified)
        VALUES (
            '{uuid.uuid4()}',
            '{TENANT_A_ID}',
            'admin@bloom-florista.test',
            '{_DEV_HASH}',
            'tenant_admin',
            true, false, true
        )
    """))

    # Seed admin user for Tenant B — switch RLS context first
    conn.execute(sa.text(
        f"SELECT set_config('app.tenant_id', '{TENANT_B_ID}', TRUE)"
    ))
    conn.execute(sa.text(f"""
        INSERT INTO users (id, tenant_id, email, hashed_password, role, is_active, is_superuser, is_verified)
        VALUES (
            '{uuid.uuid4()}',
            '{TENANT_B_ID}',
            'admin@acme-plumbing.test',
            '{_DEV_HASH}',
            'tenant_admin',
            true, false, true
        )
    """))

    # Platform manager — tenant_id IS NULL, visible under any RLS context
    conn.execute(sa.text(f"""
        INSERT INTO users (id, tenant_id, email, hashed_password, role, is_active, is_superuser, is_verified)
        VALUES (
            '{uuid.uuid4()}',
            NULL,
            'platform@concierge.test',
            '{_DEV_HASH}',
            'tenant_manager',
            true, false, true
        )
    """))

    # Seed default agent_config for each tenant
    conn.execute(sa.text(
        f"SELECT set_config('app.tenant_id', '{TENANT_A_ID}', TRUE)"
    ))
    conn.execute(sa.text(f"""
        INSERT INTO agent_config (id, tenant_id, persona_name, persona_description)
        VALUES ('{uuid.uuid4()}', '{TENANT_A_ID}', 'Flora', 'A friendly floral concierge for Bloom Florista.')
    """))

    conn.execute(sa.text(
        f"SELECT set_config('app.tenant_id', '{TENANT_B_ID}', TRUE)"
    ))
    conn.execute(sa.text(f"""
        INSERT INTO agent_config (id, tenant_id, persona_name, persona_description)
        VALUES ('{uuid.uuid4()}', '{TENANT_B_ID}', 'Max', 'A knowledgeable plumbing assistant for ACME Plumbing.')
    """))


def downgrade() -> None:
    # Drops everything — only safe in development. Never run in production.
    conn = op.get_bind()

    for table in RLS_FORCE_TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))

    conn.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON users"))

    op.drop_table("tenant_costs")
    op.drop_table("audit_log")
    op.drop_table("escalations")
    op.drop_table("leads")
    op.drop_table("chunks")
    op.drop_table("cms_pages")
    op.drop_table("agent_config")
    op.drop_table("widgets")
    op.drop_table("users")
    op.drop_table("tenants")

    conn.execute(sa.text("DROP EXTENSION IF EXISTS vector"))
