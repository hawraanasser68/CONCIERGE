"""Backfill missing updated_at columns on TimestampMixin tables.

`TimestampMixin` declares created_at + updated_at on the ORM side, but the
initial schema migration was edited in-place after some DBs had already
applied it, leaving running databases out of sync with the model. Every
INSERT/SELECT against those tables blows up with UndefinedColumnError.

Uses ADD COLUMN IF NOT EXISTS so the migration is safe on databases that
already have the column (fresh installs from the corrected 0001).

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Tables whose ORM model inherits TimestampMixin and therefore needs updated_at.
_TIMESTAMPED_TABLES = ("widgets", "cms_pages", "chunks", "leads", "escalations")


def upgrade() -> None:
    for table in _TIMESTAMPED_TABLES:
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD COLUMN IF NOT EXISTS updated_at "
            f"TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        )


def downgrade() -> None:
    for table in _TIMESTAMPED_TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS updated_at")
