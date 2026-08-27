# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-06-04

### Added
- Complete User Profile page redesign featuring a new premium glassmorphic UI.
- Avatar upload functionality with client-side Base64 image compression.
- Persistent avatar storage in the `users` database table.

### Fixed
- Fixed broken test suite caused by ASGI `CORSMiddleware` wrapping in `main.py` affecting dependency overrides.
- Fixed GitHub Actions test suite failures caused by unexpected environment variables during Pydantic Settings validation.

## [1.0.2] - 2026-05-19

### Changed
- Overhauled global design system to a premium light theme with refined typography (Inter & Outfit).
- Restructured navigation: 6 primary tabs + "More" dropdown on Desktop, 5 tabs + Menu drawer on Mobile.
- Added a prominent central "+" (Add) button in the mobile bottom navigation bar and removed the floating action button.
- Re-designed the logo icon to a sleek geometric hexagon and cleaned up navigation brand text.
- Redesigned the Auth screen with glassmorphism styling and immersive gradient background.
- Refined Dashboard KPI cards, custom chart tooltips, and budget progress indicators.

## [1.0.1] - 2026-05-19

### Added
- Dashboard time-range filters (This Month, 3 Months, Current Year, All Time)
- Delete functionality for Amadeus AI conversations

### Changed
- Renamed "AI Advisor" to "Amadeus AI" across the platform
- Improved AI Advisor context injection to explicitly include current date to prevent temporal hallucinations

### Fixed
- Fixed bug where Budget progress tracked all-time spending instead of current monthly spending
- Fixed cascade delete error when removing Amadeus AI conversations

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
