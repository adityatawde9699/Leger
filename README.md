<div align="center">

# Ledger

**AI-Native Personal Finance Platform**

Track expenses, automate categorization, scan receipts, manage investments,
and get AI-powered financial insights — all with local-first privacy.

[![CI](https://github.com/adityatawde9699/Leger/actions/workflows/ci.yml/badge.svg)](https://github.com/adityatawde9699/Leger/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Vite + React)                      │
│  Dashboard │ Transactions │ Budgets │ Investments │ Amadeus AI      │
│  Accounts  │ Credit Health│ Export  │ Audit/Webhooks│ Command (⌘K)  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ REST + SSE
┌───────────────────────────────▼─────────────────────────────────────┐
│                      BACKEND (FastAPI + SQLAlchemy)                  │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Auth     │  │ CRUD     │  │ Import   │  │ AI Router        │   │
│  │ Guard    │  │ Endpoints│  │ Pipeline │  │ (rules → Groq    │   │
│  │(Supabase)│  │ (35+)    │  │ (CSV/PDF)│  │  → Cerebras →..) │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────┬──────────┘   │
│                                                     │              │
│  ┌──────────────────────────────────────────────────▼────────────┐ │
│  │                    AI SERVICE LAYER                           │ │
│  │  Auto-Categorizer │ Proactive Insights │ Receipt OCR         │ │
│  │  Bill Negotiator  │ Credit Health      │ Community Benchmarks│ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ Audit Logger     │  │ Webhook    │  │ GST Engine + Export    │ │
│  │ (append-only)    │  │ Dispatcher │  │ (CSV/JSON/Tally XML)   │ │
│  └──────────────────┘  └────────────┘  └────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼──────────────────────┐
        ▼                       ▼                      ▼
┌──────────────┐  ┌───────────────────────────┐  ┌───────────────────┐
│  PostgreSQL  │  │ Multi-Provider AI Router  │  │ Vision OCR (LLM)  │
│  (psycopg3)  │  │ (Groq/Cerebras/Gemini/..) │  │ (Gemini receipts) │
└──────────────┘  └───────────────────────────┘  └───────────────────┘
```

## Features

| Category | Features |
|---|---|
| **Core** | Transactions, multi-account management, budgets & goals, recurring payment detection |
| **AI** | Auto-categorization (rules + LLM), proactive insights, Amadeus AI chat (SSE), receipt OCR, bill negotiation |
| **Analytics** | Dashboard KPIs (w/ time filters), category breakdowns, credit health score (300-900), community benchmarks |
| **Investments** | Portfolio tracking (stocks/MF/crypto/FD/gold), holdings with live P&L |
| **Compliance** | GST computation (Indian tax), audit logging, webhook integrations, Tally XML export |
| **Platform** | Installable PWA (offline support, app shortcuts, maskable icon), command palette (⌘K), data export (CSV/JSON/Tally) |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+ (or use SQLite for development)

### 1. Clone

```bash
git clone https://github.com/adityatawde9699/Leger.git
cd ledger
```

### 2. Backend

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env    # Edit with your values
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App is live at **http://127.0.0.1:5173** — backend API at **http://127.0.0.1:8000/docs**.

The app is an installable PWA — open it in a supporting browser and choose **Install** to add it to your home screen / desktop, with offline support and app shortcuts (Add transaction, Dashboard, Amadeus AI).

**Brand icons** live in `frontend/public/`. The sources of truth are `favicon.svg` (rounded tab/`any` icon) and `maskable-icon.svg` (full-bleed safe-zone icon); every raster artifact (`favicon.ico`, the `pwa-*`, `apple-touch-icon`, and `maskable-*` PNGs) is generated from them:

```bash
cd frontend
npm run icons   # regenerate after editing either SVG
```

### 4. (Optional) Configure AI Providers

Ledger uses a multi-provider fallback router for maximum availability and zero cost. Set at least one of these keys in your `backend/.env` file:

```bash
GROQ_API_KEY="your_groq_key"
GEMINI_API_KEY="your_gemini_key"
CEREBRAS_API_KEY="your_cerebras_key"
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | `sqlite:///./ledger_dev.db` | PostgreSQL or SQLite connection string |
| `AUTH_PROVIDER` | Yes | `dev` | Auth mode: `dev`, `supabase`, or `firebase` |
| `ENVIRONMENT` | No | `development` | `development`, `staging`, or `production` |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Comma-separated allowed origins |
| `GROQ_API_KEY` | No | — | Groq API key (primary) |
| `GEMINI_API_KEY` | No | — | Gemini API key (multimodal extraction) |
| `CEREBRAS_API_KEY` | No | — | Cerebras API key (high speed fallback) |
| `SUPABASE_JWKS_URL` | If Supabase | — | Supabase JWKS URL for JWT verification |
| `FIREBASE_PROJECT_ID` | If Firebase | — | Firebase project ID for JWT verification |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis URL for caching |
| `ADVISOR_RATE_LIMIT` | No | `10/minute` | Rate limit for Amadeus AI endpoint |
| `DEBUG` | No | `false` | Enable debug logging |

> ⚠️ **Production:** `AUTH_PROVIDER=dev` is **blocked** in `ENVIRONMENT=production`. The app will refuse to start.

## API Endpoints

<details>
<summary>Click to expand (35+ endpoints)</summary>

| Method | Path | Description |
|---|---|---|
| **Transactions** | | |
| `GET` | `/transactions` | List (paginated, filtered) |
| `POST` | `/transactions` | Create |
| `PUT` | `/transactions/{id}` | Update |
| `DELETE` | `/transactions/{id}` | Delete |
| **Accounts** | | |
| `GET` | `/accounts` | List user accounts |
| `POST` | `/accounts` | Create account |
| `PUT` | `/accounts/{id}` | Update account |
| `DELETE` | `/accounts/{id}` | Delete account |
| **Budgets** | | |
| `GET` | `/budgets` | List budgets |
| `POST` | `/budgets` | Create budget |
| `PUT` | `/budgets/{id}` | Update budget |
| `DELETE` | `/budgets/{id}` | Delete budget |
| **Import** | | |
| `POST` | `/sms/parse` | Parse UPI SMS |
| `POST` | `/import/csv` | Import CSV statement |
| `POST` | `/import/pdf` | Import PDF statement |
| **AI Services** | | |
| `POST` | `/categorize` | Auto-categorize single |
| `POST` | `/categorize/batch` | Batch categorize |
| `POST` | `/receipt/scan` | Receipt OCR |
| `GET` | `/insights/proactive` | AI-generated insights |
| `GET` | `/bills/negotiate` | Bill negotiation advice |
| `POST` | `/advisor` | Amadeus AI chat (SSE streaming) |
| **Analytics** | | |
| `GET` | `/summary` | Monthly summary |
| `GET` | `/credit-health` | Credit health score |
| `GET` | `/benchmarks` | Community benchmarks |
| `GET` | `/gst/report` | GST slab report |
| **Investments** | | |
| `GET/POST/DELETE` | `/portfolios` | Portfolio CRUD |
| `GET/POST` | `/portfolios/{id}/holdings` | Holdings management |
| `PUT/DELETE` | `/holdings/{id}` | Update/delete holding |
| `GET` | `/portfolios/summary` | Aggregate P&L |
| **Platform** | | |
| `GET` | `/export/{csv\|json\|tally}` | Data export |
| `GET` | `/audit` | Audit trail |
| `GET/POST/DELETE` | `/webhooks` | Webhook management |

</details>

## Project Structure

```
ledger/
├── .github/
│   ├── workflows/ci.yml          # CI pipeline
│   ├── dependabot.yml            # Dependency updates
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app + all routes
│   │   ├── models.py             # SQLAlchemy models (10 tables)
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── config.py             # Settings + production validation
│   │   ├── auth.py               # JWT verification (multi-provider)
│   │   ├── db.py                 # Database engine + session
│   │   └── services/
│   │       ├── ai_router.py      # Hybrid AI dispatcher
│   │       ├── auto_categorizer.py
│   │       ├── proactive_insights.py
│   │       ├── receipt_ocr.py
│   │       ├── bill_negotiator.py
│   │       ├── credit_health.py
│   │       ├── benchmarks.py
│   │       ├── gst.py
│   │       ├── export.py
│   │       ├── audit.py
│   │       ├── webhook_dispatcher.py
│   │       ├── insights.py
│   │       ├── prompt_guard.py
│   │       ├── sms_parser.py
│   │       └── statements.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Shell with 10 nav tabs
│   │   ├── main.jsx              # Entry point + ToastProvider
│   │   ├── lib.js                # API helpers, formatters
│   │   ├── styles.css            # Dark dual-palette design system (lime + crimson)
│   │   ├── components/
│   │   │   ├── CommandPalette.jsx # ⌘K palette (21 actions)
│   │   │   └── ui.jsx            # Toast system
│   │   └── views/
│   │       ├── Dashboard.jsx
│   │       ├── Transactions.jsx
│   │       ├── Budgets.jsx
│   │       ├── Advisor.jsx           # Amadeus AI View
│   │       ├── Accounts.jsx
│   │       ├── Investments.jsx
│   │       ├── CreditBenchmarks.jsx
│   │       ├── ExportGST.jsx
│   │       └── AuditWebhooks.jsx
│   └── package.json
├── docs/
│   └── architecture/
│       └── 001-hybrid-ai-architecture.md
└── README.md
```

## Development

```bash
# Backend linting
pip install ruff
ruff check backend/ --fix
ruff format backend/

# Backend tests
pip install pytest pytest-asyncio httpx
pytest backend/tests/ -v

# Frontend build check
cd frontend && npm run build
```

## Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [001](docs/architecture/001-hybrid-ai-architecture.md) | Hybrid AI Architecture (Local + Cloud Fallback) | Accepted |

## License

MIT
