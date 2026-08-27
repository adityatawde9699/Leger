#!/bin/sh
# Entrypoint: run DB migrations then start the server
set -e

echo "Running database migrations..."
python -c "
from app.db import Base, engine
from app.models import *  # noqa: import all models so they register

# Add new columns if they don't exist (safe for SQLite & Postgres)
from sqlalchemy import text, inspect
inspector = inspect(engine)
existing_cols = [c['name'] for c in inspector.get_columns('users')]

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

Base.metadata.create_all(bind=engine)
print('  Migrations OK')
"

echo "Starting server..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WORKERS:-1}" \
  --log-level "${LOG_LEVEL:-info}"
