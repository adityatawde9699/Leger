## Description

<!-- Clearly describe what this PR does and why. Link relevant issues. -->

Closes #

---

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ Feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix/feature that would break existing functionality)
- [ ] 📝 Documentation update
- [ ] 🔧 Refactor / chore (no functional changes)

## Checklist

### Code Quality
- [ ] My code follows the project's coding style
- [ ] I have run `ruff check` and `ruff format` on backend changes
- [ ] I have run the frontend build (`npm run build`) and it passes
- [ ] New and existing tests pass locally (`pytest tests/`)

### Database & Migrations
- [ ] I have created an Alembic migration for schema changes (`alembic revision --autogenerate`)
- [ ] Migration is reversible (has a `downgrade()` path)
- [ ] N/A — no schema changes in this PR

### Environment & Config
- [ ] New environment variables are documented in `.env.example`
- [ ] `config.py` `Settings` class has been updated for new variables
- [ ] N/A — no config changes

### Security
- [ ] No secrets, API keys, or credentials are committed
- [ ] New endpoints have proper authentication (`get_current_user` dependency)
- [ ] Rate limiting is applied to new public-facing endpoints

### Documentation
- [ ] README or relevant docs are updated
- [ ] ADR created for significant architectural decisions

## Screenshots / Recordings

<!-- If UI changes, attach before/after screenshots or screen recordings. -->
