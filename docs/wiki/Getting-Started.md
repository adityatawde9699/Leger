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
git clone https://github.com/your-username/ledger.git
cd ledger
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
3. Try adding a transaction, setting a budget, or asking the AI advisor

## Optional: Local AI with llama.cpp

For offline AI capabilities:

```bash
# Download a GGUF model (e.g., Mistral 7B Instruct)
# Run llama.cpp server
./llama-server -m models/mistral-7b-instruct-v0.3.Q4_K_M.gguf \
  --port 8080 --ctx-size 4096 --n-gpu-layers 35

# Enable in backend/.env
LLAMA_ENABLED=true
LLAMA_SERVER_URL=http://127.0.0.1:8080
```

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError` | Ensure virtual environment is activated |
| Port 8000 in use | Change port: `uvicorn app.main:app --port 8001` |
| Database connection error | Check PostgreSQL is running: `docker compose ps` |
| Frontend blank page | Check browser console for CORS errors. Verify `CORS_ORIGINS` in `.env` |
| AI features not working | Enable `LLAMA_ENABLED=true` or set `ANTHROPIC_API_KEY` |
