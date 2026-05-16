# Ledger Wiki — Home

Welcome to the Ledger Wiki. This is the central knowledge base for the AI-Native Personal Finance Platform.

## Quick Links

| Page | Description |
|---|---|
| [Getting Started](Getting-Started.md) | Installation, setup, first steps |
| [API Reference](API-Reference.md) | Complete endpoint documentation |
| [AI System](AI-System.md) | How the hybrid AI architecture works |
| [Database Schema](Database-Schema.md) | Models, relationships, migrations |
| [Deployment Guide](Deployment-Guide.md) | Production deployment checklist |

## Architecture

```
Frontend (Vite + React) → Backend (FastAPI) → PostgreSQL
                                    ↓
                           AI Router → llama.cpp (local)
                                    → Anthropic (cloud)
```

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development workflow, commit conventions, and code standards.
