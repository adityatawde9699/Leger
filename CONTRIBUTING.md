# Contributing to Ledger

Thank you for your interest in contributing to Ledger! This guide will help you get started.

## Development Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 16+ (or SQLite for development)
- Git

### First-Time Setup

```bash
# Fork and clone
git clone https://github.com/adityatawde9699/Leger.git
cd ledger

# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
pip install ruff pytest pytest-asyncio httpx  # Dev tools
cp .env.example .env

# Frontend
cd ../frontend
npm install
```

### Running Locally

```bash
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready code. Protected, requires PR review |
| `develop` | Integration branch. PRs merge here first |
| `feature/*` | New features (e.g., `feature/dark-mode`) |
| `fix/*` | Bug fixes (e.g., `fix/csv-import-encoding`) |
| `docs/*` | Documentation changes |

### Workflow

1. Create a branch from `develop`: `git checkout -b feature/your-feature develop`
2. Make changes, commit with [conventional commits](#commit-messages)
3. Push and open a PR against `develop`
4. After CI passes and review approval, it will be merged

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

| Type | When to Use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code change that neither fixes nor adds |
| `perf` | Performance improvement |
| `test` | Adding or correcting tests |
| `chore` | Build process, CI, dependencies |

**Examples:**
```
feat(ai): add bill negotiation service with LLM fallback
fix(import): handle UTF-8 BOM in CSV files
docs(readme): update environment variable table
chore(deps): bump fastapi to 0.115.6
```

## Code Standards

### Backend (Python)

- **Linter/Formatter:** [Ruff](https://docs.astral.sh/ruff/) — config in `ruff.toml`
- **Type hints:** Required on all function signatures
- **Docstrings:** Required on services, optional on simple CRUD endpoints
- **Tests:** Required for new services, located in `backend/tests/`

```bash
# Lint
ruff check backend/ --fix
ruff format backend/

# Test
pytest backend/tests/ -v
```

### Frontend (React)

- **Framework:** Vanilla React (no Next.js/Remix)
- **Styling:** Vanilla CSS — all styles in `styles.css`, no CSS-in-JS
- **State:** React hooks only, no Redux/Zustand
- **Imports:** Named imports for lucide-react icons

```bash
# Build check
cd frontend && npm run build
```

## Adding a New Feature

### Backend Service

1. Create service in `backend/app/services/your_service.py`
2. Add Pydantic schemas in `schemas.py`
3. Add SQLAlchemy models in `models.py` (if new tables)
4. Add endpoint in `main.py`
5. Add audit logging via `log_event()` for data mutations
6. Write tests in `backend/tests/test_your_service.py`

### Frontend View

1. Create view in `frontend/src/views/YourView.jsx`
2. Add CSS classes in `styles.css` under a section comment
3. Wire into `App.jsx` nav and switch
4. Add command palette entry in `CommandPalette.jsx`

## Database Changes

- Always create an Alembic migration: `alembic revision --autogenerate -m "description"`
- Ensure `downgrade()` is functional
- Test migration on a fresh DB before submitting PR

## Security

- Never commit `.env` files, API keys, or credentials
- All new endpoints must use `Depends(get_current_user)`
- Apply rate limiting to AI/public endpoints via `slowapi`
- See [SECURITY.md](SECURITY.md) for vulnerability reporting

## Getting Help

- Open an [issue](https://github.com/adityatawde9699/Leger/issues) for bugs or features
- Check existing issues and PRs before creating new ones
- Tag issues with appropriate labels

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
