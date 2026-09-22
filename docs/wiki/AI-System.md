# AI System Architecture

## Overview

Ledger uses a hybrid architecture that prioritizes deterministic financial calculations, graceful degradation, and explicit provider disclosure. AI is optional. When configured, the backend uses a custom multi-provider cloud router:

```text
Request → deterministic service/rules → (optional) Multi-Provider AI Router (Groq → Cerebras → Gemini → Cohere → OpenRouter) → Graceful Fallback
```

## Layer 1: Rule Engine

Zero-latency deterministic rules handle ~70% of operations:

| Service | Rule Engine Coverage |
|---|---|
| Auto-Categorizer | 50+ keyword patterns for Indian merchants (Swiggy, Zomato, Ola, Amazon, etc.) |
| GST Computation | Full rate mapping table — no AI needed |
| Budget Alerts | Mathematical threshold comparison |
| Recurring Detection | Frequency + amount pattern matching |

**When rules are sufficient, the LLM is never called.**

## Layer 2: Multi-Provider AI Router (`services/ai_router.py`)

For operations that need language understanding, Ledger uses a custom AI router that cascades through configured providers. The router does not silently claim local processing: advisor metadata discloses the configured cloud provider names, while deterministic questions bypass the router entirely.

**Fallback Chain:**
1. **Groq** (`llama-3.1-8b-instant`) — Extremely fast, primary choice for extraction and categorization.
2. **Cerebras** (`llama-3.3-70b`) — High intelligence, ultra-low latency fallback.
3. **Gemini** (`gemini-1.5-flash`) — Robust multimodal model used for extraction and enrichment.
4. **Cohere** (`command-r-plus-08-2024`) — High quality fallback.
5. **OpenRouter** (`meta-llama/llama-3-8b-instruct:free`) — Final fallback.

**Activation:** Set at least one provider API key (e.g., `GROQ_API_KEY`) in `.env`.

### Used For
- Complex transaction categorization
- Proactive financial insights
- Structuring raw OCR text from receipts
- Bill negotiation strategies
- Amadeus AI conversations (SSE streaming)

## Layer 3: Graceful Degradation

**No endpoint ever returns a 500 due to AI unavailability.** When all AI layers fail:
- Auto-categorizer returns `"Other"` with low confidence
- Insights returns empty array
- Advisor returns "AI unavailable" message
- Receipt OCR returns error details

## AI trust contract

Direct factual advisor questions are routed through `backend/app/services/advisor_facts.py` before any model call. Ledger performs the arithmetic, returns evidence transaction IDs and assumptions, and the UI labels the response “Calculated by Ledger.” Open-ended interpretation and planning remain AI-assisted and are labeled “Explained by AI.”

AI-generated proactive insights are accepted only when they cite at least one transaction ID that exists in the current user dataset. The API returns the cited evidence, confidence, source (`rules` or `ai`), action, and data-quality metadata. The system asks for *at most* five insights and may return fewer when the data does not support more.

Direct factual questions should be answered from deterministic Ledger calculations whenever possible. Cloud-model output is explanatory and must not invent balances, transactions, market data, or tax conclusions.

## AI Services

### Auto-Categorizer (`services/auto_categorizer.py`)

```text
Description → Keyword Rules (instant)
                 ↓ if "Other" or low confidence
              LLM categorization with JSON schema
                 ↓ parse response
              Category + Confidence (0.0-1.0)
```

### Proactive Insights (`services/proactive_insights.py`)

Generates 4 insight types from spending data:
- ⚠️ **Warning** — Budget overruns, unusual spikes
- 💡 **Tip** — Cost-saving opportunities
- ✅ **Positive** — Good financial habits
- ℹ️ **Info** — Interesting trends

Recurring-payment detection is deterministic and now reports cadence, amount range, active/stale status, confidence, and transaction evidence. Repeated descriptions are treated as leads, not confirmed subscriptions.

### Receipt OCR (`services/receipt_ocr.py` & `services/statements.py`)

Uses a two-step OCR to LLM extraction pipeline:
1. Accepts image or PDF
2. **PaddleOCR / Tesseract** extracts raw text boundaries
3. Extracted raw text is sent to the AI Router to be semantically enriched and structured.
4. Returns structured schema (merchant, amount, date, items, category)

### Bill Negotiator (`services/bill_negotiator.py`)

1. Identifies recurring payments from transaction history
2. Generates negotiation scripts per merchant
3. Estimates savings potential
4. Suggests alternative services

### Credit Health (`services/credit_health.py`)

Behavioral scoring (300-900) with 5 factors:
- Savings rate (25%)
- Budget adherence (25%)
- Spending consistency (20%)
- Category diversification (15%)
- Credit utilization proxy (15%)

## Prompt Security

### Prompt Guard (`services/prompt_guard.py`)

All user inputs to AI services pass through sanitization:
- Strips injection attempts (system prompt overrides)
- Enforces maximum input length
- Escapes potentially harmful characters
- Logs suspicious inputs for review

### System Prompts

Every AI service uses a strict system prompt that:
- Defines the exact output format (JSON schema)
- Restricts the response to financial data only
- Instructs the model to refuse non-financial queries

## Configuration Summary

| Variable | Required | Impact |
|---|---|---|
| `GROQ_API_KEY` | No | Enables Groq fallback layer |
| `CEREBRAS_API_KEY` | No | Enables Cerebras fallback layer |
| `GEMINI_API_KEY` | No | Enables Gemini fallback layer |
| `COHERE_API_KEY` | No | Enables Cohere fallback layer |
| `OPENROUTER_API_KEY` | No | Enables OpenRouter fallback layer |

**Minimum viable setup:** No AI configured. The app works fully with rule-based features only.
