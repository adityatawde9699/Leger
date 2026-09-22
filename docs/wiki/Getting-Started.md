# Getting Started

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Backend runtime |
| Node.js | 20+ | Frontend toolchain |
| PostgreSQL | 16+ | Production database |
| Docker | 24+ | Database services (optional) |

## Step 1: Clone the Repository

```bash
git clone https://github.com/adityatawde9699/Leger.git
cd Leger
```

## Step 2: Start Database Services

```bash
docker compose up -d
# PostgreSQL on :5432, Redis on :6379
```

Or install PostgreSQL manually and create the database:
```sql
CREATE DATABASE ledger;
CREATE USER ledger WITH PASSWORD 'ledger';
GRANT ALL PRIVILEGES ON DATABASE ledger TO ledger;
```

## Step 3: Backend Setup

```bash
cd backend
python -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
source .venv/bin/activate       # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database URL and settings

# Start server
uvicorn app.main:app --reload --port 8000
```

The API documentation is available at **http://127.0.0.1:8000/docs** (Swagger UI).

## Step 4: Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The app is available at **http://127.0.0.1:5173**.

## Step 5: Verify

1. Open http://127.0.0.1:5173 in your browser
2. The app will use `AUTH_PROVIDER=dev` by default (accepts any Bearer token)
3. Try adding a transaction, setting a budget, or asking the Amadeus AI

## Optional: cloud AI providers

Ledger's core ledger, import, analytics, goals, and deterministic advisor facts work without an AI key. To enable open-ended advisor explanations, set one or more supported provider keys in `backend/.env`:

```bash
GROQ_API_KEY=...
# Optional fallbacks:
CEREBRAS_API_KEY=...
GEMINI_API_KEY=...
COHERE_API_KEY=...
OPENROUTER_API_KEY=...
```

The advisor discloses configured provider names in its metadata. Do not describe a deployment as local/offline AI unless a separate local provider has actually been deployed; the current router is cloud-provider based.

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError` | Ensure virtual environment is activated |
| Port 8000 in use | Change port: `uvicorn app.main:app --port 8001` |
| Database connection error | Check PostgreSQL is running: `docker compose ps` |
| Frontend blank page | Check browser console for CORS errors. Verify `CORS_ORIGINS` in `.env` |
| AI features not working | Set at least one supported provider key; direct factual answers still work without AI |
