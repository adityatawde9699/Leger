# Ledger Wiki — Home

Welcome to the Ledger Wiki. This is the central knowledge base for the AI-Native Personal Finance Platform.

## Quick Links

| Page | Description |
|---|---|
| [Getting Started](Getting-Started.md) | Installation, setup, first steps |
| [API Reference](API-Reference.md) | Complete endpoint documentation |
| [AI System](AI-System.md) | How the hybrid AI architecture works |
| [Data Dictionary](Data-Dictionary.md) | Transaction semantics and calculation contract |
| [Database Schema](Database-Schema.md) | Models, relationships, migrations |
| [Deployment Guide](Deployment-Guide.md) | Production deployment checklist |
| [Release Checklist](../RELEASE-CHECKLIST.md) | Financial correctness and release-safety checklist |

## Architecture

```
Frontend (Vite + React) → Backend (FastAPI) → PostgreSQL
                                    ↓
                    deterministic services / Ledger facts
                                    ↓
                    optional configured cloud AI router
```

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development workflow, commit conventions, and code standards.
