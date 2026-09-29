# Deployment Guide

## Production Checklist

### Environment
```bash
ENVIRONMENT=production
AUTH_PROVIDER=google       # Google Identity Services; NEVER dev in production
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/ledger?sslmode=require
CORS_ORIGINS=https://your-domain.com
UPSTASH_REDIS_REST_URL=https://your-database.upstash.io
UPSTASH_REDIS_REST_TOKEN=<rest-token>
WEBHOOK_ENCRYPTION_KEYS=<fernet-key>
BACKUP_ENCRYPTION_KEY=<different-fernet-key>
BACKUP_PREVIOUS_ENCRYPTION_KEYS=
```

> ⚠️ App refuses to start with `AUTH_PROVIDER=dev` in production.
Generate each Fernet key with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
Keep the backup and webhook keys separate and store them in your deployment secret manager.
For webhook key rotation, prepend a new key to `WEBHOOK_ENCRYPTION_KEYS` separated by a comma;
existing records can still be decrypted with the old key. Re-encrypt existing records with the
new key before removing the old key. When rotating backups, move the former
`BACKUP_ENCRYPTION_KEY` into `BACKUP_PREVIOUS_ENCRYPTION_KEYS` and set a new primary key.
Keep old keys until those encrypted backups expire or have been re-encrypted.
For Upstash, copy the HTTPS endpoint and REST token from the database's REST tab into
`UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`. Do not use the TCP connection URL
or the `redis-cli` command for these settings.

The API uses a 12-hour Secure, HttpOnly, SameSite=Lax session cookie. Production browser requests
use the frontend's same-origin `/api` rewrite; update `frontend/vercel.json` if the backend URL
changes. Set `CORS_ORIGINS` to the exact frontend origin; cookie-authenticated writes from
other origins are rejected. Run an unauthorized `GET /api/profile` smoke check after deployment:
it must return 401 and include `X-Content-Type-Options: nosniff` and `X-Request-ID`.
Run `python scripts/security_smoke.py https://your-frontend-domain` after setting deployment
secrets and verify the same origin is configured in Google Identity Services.

### Security Checks
- [ ] Auth provider is NOT `dev`
- [ ] Database uses SSL
- [ ] CORS restricted to your domain(s)
- [ ] API keys via secrets manager
- [ ] `DEBUG=false`
- [ ] Shared Redis is available to every API worker
- [ ] Webhook and backup keys are present and different
- [ ] Unauthorized `/profile` returns 401; production `/docs` returns 404

### Backend Deploy (Gunicorn)
```bash
pip install gunicorn
gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:8000
```

### Frontend Deploy
Set `VITE_AUTH_PROVIDER=google` and `VITE_GOOGLE_CLIENT_ID` to the same Web
OAuth client ID. In Google Cloud Console, add the deployed frontend URL and
local development URL to the client's **Authorized JavaScript origins**.

```bash
npm run build
# Deploy dist/ to Vercel, Netlify, or Cloudflare Pages
```

### Database
```bash
alembic upgrade head
```

### Daily Backups
```bash
pg_dump -h localhost -U ledger ledger | gzip > backup_$(date +%Y%m%d).sql.gz
```
