#!/bin/sh
# Entrypoint: run DB migrations then start the server
set -e

echo "Running database migrations..."
python - <<'PY'
from app.db import Base, engine
from app.models import *  # noqa: import all models so they register
from sqlalchemy import text, inspect

# 1. Create any missing tables first (fresh DBs get every column from the model).
Base.metadata.create_all(bind=engine)

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
