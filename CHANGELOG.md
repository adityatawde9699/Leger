# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-06-16

### Added
- Proper brand **favicon** set generated from the in-app Ledger mark (lime squircle, dark "L" monogram + ascending bars, crimson tall bar): `favicon.svg`, multi-resolution `favicon.ico` (16/32/48), 16/32px PNGs, and a 180px `apple-touch-icon`.
- **Installable PWA** polish: dedicated `maskable` icon (mark kept within the 80% safe zone so OS shape masks never clip it) and home-screen **app shortcuts** — Add transaction, Dashboard, and Amadeus AI.
- Deep-linking via a `?view=` query param so manifest shortcuts open the right screen.
- `frontend/public/maskable-icon.svg` source and a reproducible `npm run icons` generator (`scripts/generate-icons.mjs`, powered by `sharp`).

### Changed
- PWA manifest `theme_color`/`background_color` now match the dark dual-palette brand (`#0A0A0B`) instead of the legacy indigo/light values, so the install splash screen and OS chrome stay on-brand. Added `categories` metadata.

### Fixed
- `env(safe-area-inset-*)` rules now actually apply: added `viewport-fit=cover` to the viewport meta (previously the insets resolved to 0 on iOS), and the mobile header now extends under the status bar / notch in standalone mode. Bottom nav respects left/right insets in landscape.
- Replaced the home-screen/tab icon, which pointed at a 398 KB JPEG mislabeled as `pwa-512x512.png`, with correctly sized, lightweight PNGs (512px icon: 398 KB → ~16 KB).

## [1.3.0] - 2026-06-13

### Added
- New **Ledger** brand identity: a redesigned logo — an "L" monogram beside an ascending bar chart (growth / ledger entries) in the lime + crimson dual palette — replacing the previous owl mark.
- Dark dual-palette design system: neon-lime primary (actions / income / positive) and crimson accent (expenses / alerts / danger), with condensed display numerals for hero and KPI figures.
- Reusable layout utilities (`.view-header`, `.summary-strip`, `.stat-card`, `.icon-chip`, `.empty-state`).
- Authoritative responsive layer with refined tablet and mobile breakpoints: full-width header actions, single-column grids, collapsed transaction rows, larger touch targets, and safe-area-aware padding.

### Changed
- Renamed the web app from "Leger" to **Ledger** across the UI (page title, sidebar, auth screen, PWA manifest).
- Receipt OCR now runs entirely through the Gemini vision model.

### Fixed
- Restored ~200 component styles that were dropped during the dark-theme migration, so all views render fully styled (Profile, Investments, Advisor, Credit, Audit/Webhooks, Export/GST, Command Palette, Auth).
- Purged stray light-theme colors from every view and corrected semantic colors (income → lime, expenses/alerts → crimson).
- Transaction rows no longer overflow on phones and tablets (wide grid collapses to a stacked card layout).

### Performance
- Removed unused `paddleocr` / `pytesseract` dependencies (hundreds of MB) — smaller image, lower memory, and faster cold starts on Render's free tier.
- `_get_balance_at` now uses a single SQL aggregate instead of an O(n²) Python loop during statement import.
- Eager-loaded portfolio holdings (fixed N+1), batched statement-import de-duplication into one query, and added an optional `RUN_DB_BOOTSTRAP` flag to skip redundant startup DDL.

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
