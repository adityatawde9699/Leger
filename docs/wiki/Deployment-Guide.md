# Deployment Guide

## Production Checklist

### Environment
```bash
ENVIRONMENT=production
AUTH_PROVIDER=google
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/ledger?sslmode=require
CORS_ORIGINS=https://your-domain.com
```

> ⚠️ Google OAuth must be configured before deploying the app in production.

### Security Checks
- [ ] Auth provider is `google`
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
