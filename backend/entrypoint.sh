#!/bin/sh
# Entrypoint: run DB migrations then start the server
set -e

echo "Running database migrations..."
python - <<'PY'
from app.db import Base, engine
from app.models import *  # noqa: import all models so they register
from sqlalchemy import text, inspect
from app.db import SessionLocal
from app.services.webhook_secrets import migrate_plaintext_secrets

# 1. Create any missing tables first (fresh DBs get every column from the model).
Base.metadata.create_all(bind=engine)
if engine.dialect.name == 'postgresql':
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE webhooks ALTER COLUMN secret TYPE TEXT'))
session_cols = [c['name'] for c in inspect(engine).get_columns('app_sessions')]
if 'reauthed_at' not in session_cols:
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE app_sessions ADD COLUMN reauthed_at TIMESTAMP'))
        conn.execute(text('UPDATE app_sessions SET reauthed_at = created_at WHERE reauthed_at IS NULL'))
with SessionLocal() as db:
    migrated = migrate_plaintext_secrets(db)
    print(f'Encrypted {migrated} legacy webhook secrets')

# 2. Ad-hoc column adds for pre-existing 'users' tables (Alembic is not configured).
existing_cols = [c['name'] for c in inspect(engine).get_columns('users')]
with engine.begin() as conn:
    if 'display_name' not in existing_cols:
        conn.execute(text('ALTER TABLE users ADD COLUMN display_name VARCHAR(128)'))
        print('  + Added users.display_name')
    if 'currency_preference' not in existing_cols:
        # SQLite: default handled in app; Postgres: add with default
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN currency_preference VARCHAR(3) NOT NULL DEFAULT 'INR'"))
        except Exception:
            conn.execute(text('ALTER TABLE users ADD COLUMN currency_preference VARCHAR(3)'))
        print('  + Added users.currency_preference')
    if 'avatar_url' not in existing_cols:
        conn.execute(text('ALTER TABLE users ADD COLUMN avatar_url TEXT'))
        print('  + Added users.avatar_url')
    if 'region' not in existing_cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN region VARCHAR(16) NOT NULL DEFAULT 'IN'"))
        print('  + Added users.region')
    if 'income_pattern' not in existing_cols:
        conn.execute(text('ALTER TABLE users ADD COLUMN income_pattern VARCHAR(16)'))
        print('  + Added users.income_pattern')
    if 'pay_cycle' not in existing_cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN pay_cycle VARCHAR(16) NOT NULL DEFAULT 'monthly'"))
        print('  + Added users.pay_cycle')
    if 'risk_comfort' not in existing_cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN risk_comfort VARCHAR(16) NOT NULL DEFAULT 'not_sure'"))
        print('  + Added users.risk_comfort')
    if 'household_mode' not in existing_cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN household_mode VARCHAR(16) NOT NULL DEFAULT 'individual'"))
        print('  + Added users.household_mode')
    if 'recurring_tolerance' not in existing_cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN recurring_tolerance VARCHAR(16) NOT NULL DEFAULT 'standard'"))
        print('  + Added users.recurring_tolerance')
    if 'onboarding_completed' not in existing_cols:
        conn.execute(text('ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE'))
        print('  + Added users.onboarding_completed')
    if 'cloud_ai_enabled' not in existing_cols:
        conn.execute(text('ALTER TABLE users ADD COLUMN cloud_ai_enabled BOOLEAN NOT NULL DEFAULT TRUE'))
        print('  + Added users.cloud_ai_enabled')
    if 'insight_frequency' not in existing_cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN insight_frequency VARCHAR(16) NOT NULL DEFAULT 'daily'"))
        print('  + Added users.insight_frequency')
    if 'obligations_reviewed_at' not in existing_cols:
        conn.execute(text('ALTER TABLE users ADD COLUMN obligations_reviewed_at TIMESTAMP'))
        print('  + Added users.obligations_reviewed_at')
    job_cols = [c['name'] for c in inspect(engine).get_columns('import_jobs')]
    if 'file_extension' not in job_cols:
        conn.execute(text("ALTER TABLE import_jobs ADD COLUMN file_extension VARCHAR(8) DEFAULT ''"))
        print('  + Added import_jobs.file_extension')
    if 'file_fingerprint' not in job_cols:
        conn.execute(text("ALTER TABLE import_jobs ADD COLUMN file_fingerprint VARCHAR(64)"))
        print('  + Added import_jobs.file_fingerprint')
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_import_jobs_file_fingerprint ON import_jobs (file_fingerprint)'))
    if 'account_id' not in job_cols:
        conn.execute(text('ALTER TABLE import_jobs ADD COLUMN account_id VARCHAR(36)'))
        print('  + Added import_jobs.account_id')
    if 'file_content' not in job_cols:
        blob_type = 'BYTEA' if engine.dialect.name == 'postgresql' else 'BLOB'
        conn.execute(text(f'ALTER TABLE import_jobs ADD COLUMN file_content {blob_type}'))
        print('  + Added import_jobs.file_content')
    if 'total_rows' not in job_cols:
        conn.execute(text('ALTER TABLE import_jobs ADD COLUMN total_rows INTEGER'))
        print('  + Added import_jobs.total_rows')
    if 'processed_rows' not in job_cols:
        conn.execute(text('ALTER TABLE import_jobs ADD COLUMN processed_rows INTEGER NOT NULL DEFAULT 0'))
        print('  + Added import_jobs.processed_rows')
    if 'cancel_requested' not in job_cols:
        conn.execute(text('ALTER TABLE import_jobs ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT FALSE'))
        print('  + Added import_jobs.cancel_requested')
    if 'excluded_row_fingerprints' not in job_cols:
        conn.execute(text("ALTER TABLE import_jobs ADD COLUMN excluded_row_fingerprints TEXT"))
        print('  + Added import_jobs.excluded_row_fingerprints')
    if 'review_overrides' not in job_cols:
        conn.execute(text("ALTER TABLE import_jobs ADD COLUMN review_overrides TEXT"))
        print('  + Added import_jobs.review_overrides')
    account_cols = [c['name'] for c in inspect(engine).get_columns('accounts')]
    if 'last_reconciled_at' not in account_cols:
        conn.execute(text('ALTER TABLE accounts ADD COLUMN last_reconciled_at TIMESTAMP'))
        print('  + Added accounts.last_reconciled_at')
    if 'last_reconciled_balance' not in account_cols:
        conn.execute(text('ALTER TABLE accounts ADD COLUMN last_reconciled_balance NUMERIC(14,2)'))
        print('  + Added accounts.last_reconciled_balance')
    if 'reconciliation_note' not in account_cols:
        conn.execute(text('ALTER TABLE accounts ADD COLUMN reconciliation_note TEXT'))
        print('  + Added accounts.reconciliation_note')
    if 'credit_limit' not in account_cols:
        conn.execute(text('ALTER TABLE accounts ADD COLUMN credit_limit NUMERIC(14,2)'))
        print('  + Added accounts.credit_limit')
    if 'minimum_payment' not in account_cols:
        conn.execute(text('ALTER TABLE accounts ADD COLUMN minimum_payment NUMERIC(14,2)'))
        print('  + Added accounts.minimum_payment')
    if 'payment_due_date' not in account_cols:
        conn.execute(text('ALTER TABLE accounts ADD COLUMN payment_due_date DATE'))
        print('  + Added accounts.payment_due_date')
    transaction_cols = [c['name'] for c in inspect(engine).get_columns('transactions')]
    if 'status' not in transaction_cols:
        conn.execute(text("ALTER TABLE transactions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'posted'"))
        print('  + Added transactions.status')
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_transactions_status ON transactions (status)'))
print('  Migrations OK')
PY

echo "Starting server..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WORKERS:-1}" \
  --log-level "${LOG_LEVEL:-info}"
