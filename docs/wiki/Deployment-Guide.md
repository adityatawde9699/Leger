# Deployment Guide

## Production Checklist

### Environment
```bash
ENVIRONMENT=production
AUTH_PROVIDER=google       # Google Identity Services; NEVER dev in production
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/ledger?sslmode=require
CORS_ORIGINS=https://your-domain.com
```

> ⚠️ App refuses to start with `AUTH_PROVIDER=dev` in production.

### Security Checks
- [ ] Auth provider is NOT `dev`
- [ ] Database uses SSL
- [ ] CORS restricted to your domain(s)
- [ ] API keys via secrets manager
- [ ] `DEBUG=false`

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
