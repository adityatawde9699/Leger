# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-17

### Added

#### Core Platform
- Multi-account management (Savings, Credit, Wallet, Cash)
- Transaction CRUD with pagination, search, and filtering
- Budget & goals tracking with progress visualization
- Recurring payment detection
- SMS parsing for UPI transaction messages
- CSV and PDF bank statement import with SHA256 deduplication

#### AI Services
- Hybrid AI router (rules → llama.cpp local → Anthropic cloud → fallback)
- Auto-categorization engine (rule-based + LLM fallback with confidence scoring)
- Proactive financial insights (Warning, Tip, Positive, Info types)
- AI chat advisor with SSE streaming
- Receipt OCR via multimodal LLM vision (Llava-compatible)
- Bill negotiation agent with savings estimates and negotiation scripts
- Prompt injection guard for all AI inputs

#### Analytics & Health
- Dashboard with KPI cards and category breakdowns
- Credit health score (300-900) with 5-factor breakdown
- Community spending benchmarks (NSSO-adjusted percentile data)
- Monthly summary with insights

#### Investments
- Portfolio management (stocks, mutual funds, crypto, fixed deposits, gold)
- Holdings tracking with live P&L computation
- Portfolio summary with aggregate returns

#### Compliance & Export
- Indian GST engine (rate mapping, slab reports, HSN/SAC codes)
- Data export in CSV, JSON, and Tally Prime/ERP 9 XML formats
- Append-only audit logging for all data mutations
- Webhook system with HMAC-SHA256 signing and auto-disable

#### Platform
- PWA with offline support and service worker
- Command palette (⌘K / Ctrl+K) with 21 actions
- Toast notification system
- Skeleton loading states
- Responsive design with mobile breakpoints

#### DevOps
- GitHub Actions CI (ruff lint, pytest, frontend build)
- Dependabot for pip, npm, and GitHub Actions
- PR template with migration/security checklists
- Issue templates (bug report, feature request)
- Architecture Decision Records (ADRs)
- Security policy with responsible disclosure

### Security
- JWT authentication (multi-provider: Supabase, Firebase, dev)
- Production hard-block for `AUTH_PROVIDER=dev`
- Rate limiting on all endpoints via slowapi
- CORS restricted to configured origins
- No raw SQL queries (SQLAlchemy ORM only)
