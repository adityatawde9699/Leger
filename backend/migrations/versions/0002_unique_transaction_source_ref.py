"""Enforce one transaction per (user, source, source_ref).

Import, SMS and offline de-duplication was check-then-insert, so two concurrent
requests could both insert the same row. Before adding the unique index, any
existing duplicates are kept (no financial data is deleted) but re-tagged with
source_ref "dup:<id>", so the earliest row keeps the identity and the extras can
be found with `WHERE source_ref LIKE 'dup:%'` and reviewed.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

INDEX = "uq_transactions_user_source_ref"
WHERE = "source_ref IS NOT NULL AND source_ref NOT LIKE 'split:%'"

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    bind = op.get_bind()
    if INDEX in {ix["name"] for ix in sa.inspect(bind).get_indexes("transactions")}:
        return
    retagged = bind.execute(sa.text(f"""
        UPDATE transactions SET source_ref = 'dup:' || id
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY user_id, source, source_ref ORDER BY created_at, id
                ) AS position
                FROM transactions WHERE {WHERE}
            ) ranked
            WHERE position > 1
        )
    """)).rowcount
    if retagged:
        logger.warning("Re-tagged %d duplicate transactions as source_ref 'dup:<id>' for review", retagged)
    op.create_index(
        INDEX, "transactions", ["user_id", "source", "source_ref"], unique=True,
        postgresql_where=sa.text(WHERE), sqlite_where=sa.text(WHERE),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="transactions")
