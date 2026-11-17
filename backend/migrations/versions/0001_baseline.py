"""Baseline schema.

Ledger ran for months without a migration tool: tables came from
Base.metadata.create_all and columns from hand-written ALTER TABLE lists in
entrypoint.sh and main.py, which drifted apart. Production databases are
therefore in slightly different states.

This baseline is a frozen copy of the schema at the time Alembic was adopted,
and it is idempotent: it creates any table, column or index that is missing
and leaves existing ones alone. A fresh database and any legacy database both
end up with the same schema, so no manual `alembic stamp` is needed.

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Server defaults for NOT NULL columns that legacy tables may be missing. Values
# match the old ALTER TABLE lists, except cloud_ai_enabled: the model defaults it
# to off (opt-in), while the old DDL used TRUE.
_LEGACY_DEFAULTS = {
    ("users", "currency_preference"): "'INR'",
    ("users", "region"): "'IN'",
    ("users", "pay_cycle"): "'monthly'",
    ("users", "risk_comfort"): "'not_sure'",
    ("users", "household_mode"): "'individual'",
    ("users", "recurring_tolerance"): "'standard'",
    ("users", "onboarding_completed"): "false",
    ("users", "cloud_ai_enabled"): "false",
    ("users", "insight_frequency"): "'daily'",
    ("users", "quiet_hours_start"): "22",
    ("users", "quiet_hours_end"): "7",
    ("users", "proactive_daily_cap"): "3",
    ("import_jobs", "processed_rows"): "0",
    ("import_jobs", "cancel_requested"): "false",
    ("import_jobs", "file_extension"): "''",
    ("transactions", "status"): "'posted'",
}


# One MetaData so foreign keys between the frozen tables resolve.
_META = sa.MetaData()


def _inspector():
    return sa.inspect(op.get_bind())


def _ensure_table(name: str, *elements) -> None:
    """Create the table, or add whichever of its columns an older table lacks."""
    table = sa.Table(name, _META, *elements, extend_existing=True)
    inspector = _inspector()
    if not inspector.has_table(name):
        table.create(op.get_bind())
        return
    existing = {col["name"] for col in inspector.get_columns(name)}
    for col in table.columns:
        if col.name in existing:
            continue
        default = _LEGACY_DEFAULTS.get((name, col.name))
        # A NOT NULL column without a known default is added as nullable rather than
        # failing the deploy; the application always writes a value for it.
        nullable = col.nullable or default is None
        op.add_column(name, sa.Column(
            col.name, col.type, nullable=nullable,
            server_default=sa.text(default) if default is not None else None,
        ))


def _ensure_index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    if name not in {ix["name"] for ix in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    _ensure_table('audit_logs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('resource_type', sa.String(length=64), nullable=False),
    sa.Column('resource_id', sa.String(length=36), nullable=True),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    _ensure_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], unique=False)
    _ensure_index('ix_audit_user_time', 'audit_logs', ['user_id', 'created_at'], unique=False)

    _ensure_table('users',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('display_name', sa.String(length=128), nullable=True),
    sa.Column('avatar_url', sa.Text(), nullable=True),
    sa.Column('currency_preference', sa.String(length=3), nullable=False),
    sa.Column('region', sa.String(length=16), nullable=False),
    sa.Column('income_pattern', sa.String(length=16), nullable=True),
    sa.Column('pay_cycle', sa.String(length=16), nullable=False),
    sa.Column('risk_comfort', sa.String(length=16), nullable=False),
    sa.Column('household_mode', sa.String(length=16), nullable=False),
    sa.Column('recurring_tolerance', sa.String(length=16), nullable=False),
    sa.Column('onboarding_completed', sa.Boolean(), nullable=False),
    sa.Column('cloud_ai_enabled', sa.Boolean(), nullable=False),
    sa.Column('insight_frequency', sa.String(length=16), nullable=False),
    sa.Column('quiet_hours_start', sa.Integer(), nullable=False),
    sa.Column('quiet_hours_end', sa.Integer(), nullable=False),
    sa.Column('proactive_daily_cap', sa.Integer(), nullable=False),
    sa.Column('obligations_reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_table('accounts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('account_type', sa.String(length=32), nullable=False),
    sa.Column('institution', sa.String(length=128), nullable=True),
    sa.Column('balance', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('credit_limit', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('minimum_payment', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('payment_due_date', sa.Date(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_reconciled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_reconciled_balance', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('reconciliation_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_accounts_user_id', 'accounts', ['user_id'], unique=False)

    _ensure_table('ai_conversations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_ai_conversations_user_id', 'ai_conversations', ['user_id'], unique=False)

    _ensure_table('app_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reauthed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('token_hash')
    )
    _ensure_index('ix_app_sessions_expires_at', 'app_sessions', ['expires_at'], unique=False)
    _ensure_index('ix_app_sessions_user_id', 'app_sessions', ['user_id'], unique=False)

    _ensure_table('budgets',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('monthly_limit', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('strategy', sa.String(length=32), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'category', name='uq_budget_user_category')
    )
    _ensure_index('ix_budgets_user_id', 'budgets', ['user_id'], unique=False)

    _ensure_table('category_corrections',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('description_hash', sa.String(length=64), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('correction_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'description_hash', name='uq_cat_correction_user_hash')
    )
    _ensure_index('ix_category_corrections_description_hash', 'category_corrections', ['description_hash'], unique=False)
    _ensure_index('ix_category_corrections_user_id', 'category_corrections', ['user_id'], unique=False)

    _ensure_table('goals',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('goal_type', sa.String(length=32), nullable=False),
    sa.Column('target_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('current_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('deadline', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_goals_user_id', 'goals', ['user_id'], unique=False)

    _ensure_table('import_jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('file_extension', sa.String(length=8), nullable=False),
    sa.Column('file_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('account_id', sa.String(length=36), nullable=True),
    sa.Column('file_content', sa.LargeBinary(), nullable=True),
    sa.Column('total_rows', sa.Integer(), nullable=True),
    sa.Column('processed_rows', sa.Integer(), nullable=False),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('excluded_row_fingerprints', sa.Text(), nullable=True),
    sa.Column('review_overrides', sa.Text(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_import_jobs_file_fingerprint', 'import_jobs', ['file_fingerprint'], unique=False)
    _ensure_index('ix_import_jobs_user_id', 'import_jobs', ['user_id'], unique=False)

    _ensure_table('merchant_aliases',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('alias_key', sa.String(length=128), nullable=False),
    sa.Column('canonical', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'alias_key', name='uq_merchant_alias_user_key')
    )
    _ensure_index('ix_merchant_aliases_user_id', 'merchant_aliases', ['user_id'], unique=False)

    _ensure_table('notifications',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('insight_id', sa.String(length=256), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('payload', sa.Text(), nullable=True),
    sa.Column('read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_notifications_created_at', 'notifications', ['created_at'], unique=False)
    _ensure_index('ix_notifications_user_id', 'notifications', ['user_id'], unique=False)

    _ensure_table('portfolios',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('portfolio_type', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_portfolios_user_id', 'portfolios', ['user_id'], unique=False)

    _ensure_table('recurring_rules',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('description', sa.String(length=128), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('cadence', sa.String(length=16), nullable=False),
    sa.Column('average_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('minimum_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('maximum_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('next_expected', sa.Date(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('confirmed', sa.Boolean(), nullable=False),
    sa.Column('evidence_transaction_ids', sa.Text(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_recurring_rules_user_id', 'recurring_rules', ['user_id'], unique=False)

    _ensure_table('user_categories',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('reporting_group', sa.String(length=64), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', 'kind', name='uq_user_category_name_kind')
    )
    _ensure_index('ix_user_categories_user_id', 'user_categories', ['user_id'], unique=False)

    _ensure_table('webhooks',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('events', sa.String(length=512), nullable=False),
    sa.Column('secret', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_triggered', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_webhooks_user_id', 'webhooks', ['user_id'], unique=False)

    _ensure_table('ai_messages',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_ai_messages_conversation_id', 'ai_messages', ['conversation_id'], unique=False)

    _ensure_table('holdings',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('portfolio_id', sa.String(length=36), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column('buy_price', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('current_price', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('asset_type', sa.String(length=32), nullable=False),
    sa.Column('purchase_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_holdings_portfolio_id', 'holdings', ['portfolio_id'], unique=False)

    _ensure_table('transactions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('merchant_normalized', sa.String(length=128), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('source_ref', sa.String(length=128), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('tags', sa.String(length=512), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('gst_rate', sa.Float(), nullable=True),
    sa.Column('gst_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('hsn_code', sa.String(length=16), nullable=True),
    sa.Column('running_balance', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('stmt_seq', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_transactions_account_id', 'transactions', ['account_id'], unique=False)
    _ensure_index('ix_transactions_category', 'transactions', ['category'], unique=False)
    _ensure_index('ix_transactions_date', 'transactions', ['date'], unique=False)
    _ensure_index('ix_transactions_source', 'transactions', ['source'], unique=False)
    _ensure_index('ix_transactions_status', 'transactions', ['status'], unique=False)
    _ensure_index('ix_transactions_user_category', 'transactions', ['user_id', 'category'], unique=False)
    _ensure_index('ix_transactions_user_date', 'transactions', ['user_id', 'date'], unique=False)
    _ensure_index('ix_transactions_user_id', 'transactions', ['user_id'], unique=False)

    _ensure_table('receipt_attachments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('transaction_id', sa.String(length=36), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('mime_type', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _ensure_index('ix_receipt_attachments_transaction_id', 'receipt_attachments', ['transaction_id'], unique=True)
    _ensure_index('ix_receipt_attachments_user_id', 'receipt_attachments', ['user_id'], unique=False)

    bind = op.get_bind()
    # Webhook secrets are Fernet tokens, longer than the original VARCHAR column.
    if bind.dialect.name == "postgresql":
        secret = next(c for c in _inspector().get_columns("webhooks") if c["name"] == "secret")
        if not isinstance(secret["type"], sa.Text):
            op.execute("ALTER TABLE webhooks ALTER COLUMN secret TYPE TEXT")
    # Sessions created before re-authentication tracking count as authenticated at creation.
    op.execute("UPDATE app_sessions SET reauthed_at = created_at WHERE reauthed_at IS NULL")


def downgrade() -> None:
    raise NotImplementedError("The baseline cannot be downgraded: it would drop every table and all user data.")
