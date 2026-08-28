#!/bin/sh
# Entrypoint: run DB migrations then start the server
set -e

echo "Running database migrations..."
python -c "
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
            conn.execute(text(\"ALTER TABLE users ADD COLUMN currency_preference VARCHAR(3) NOT NULL DEFAULT 'INR'\"))
        except Exception:
            conn.execute(text('ALTER TABLE users ADD COLUMN currency_preference VARCHAR(3)'))
        print('  + Added users.currency_preference')
    if 'avatar_url' not in existing_cols:
        conn.execute(text('ALTER TABLE users ADD COLUMN avatar_url TEXT'))
        print('  + Added users.avatar_url')
print('  Migrations OK')
"

echo "Starting server..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WORKERS:-1}" \
  --log-level "${LOG_LEVEL:-info}"
