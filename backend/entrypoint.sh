#!/bin/sh
# Entrypoint: apply database migrations, then start the server
set -e

echo "Running database migrations..."
# Alembic revisions live in backend/migrations; the baseline is idempotent, so this
# also upgrades databases created before Alembic was adopted.
python -m app.migrate

echo "Starting server..."
# Production traffic arrives through the Vercel /api rewrite and Render's proxy, so the
# socket peer is always a proxy. Trust X-Forwarded-For so per-IP limits and audit logs
# see the real client. Narrow FORWARDED_ALLOW_IPS to the proxy ranges when they are known.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" \
  --port "${PORT:-8000}" \
  --workers "${WORKERS:-1}" \
  --log-level "${LOG_LEVEL:-info}"
