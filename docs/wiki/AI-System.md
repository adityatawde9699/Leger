# AI System Architecture

## Overview

Ledger uses a hybrid AI architecture that prioritizes speed, cost, and privacy. Every AI operation follows a 4-layer fallback chain:

```
Request → Rule Engine → Local LLM (llama.cpp) → Cloud LLM (Anthropic) → Graceful Fallback
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

## Layer 2: Local LLM (llama.cpp)

For operations that need language understanding:

| Setting | Value |
|---|---|
| Server | `llama.cpp` HTTP server |
| URL | `LLAMA_SERVER_URL` (default: `http://127.0.0.1:8080`) |
| Text Model | Mistral 7B Instruct Q4_K_M |
| Vision Model | Llava 1.6 (for receipt OCR) |
| VRAM | ~6GB for 7B model |

**Activation:** Set `LLAMA_ENABLED=true` in `.env`

### Used For
- Complex transaction categorization
- Proactive financial insights
- Receipt OCR (structured data extraction from images)
- Bill negotiation strategies

## Layer 3: Cloud LLM (Anthropic)

Used when local LLM is unavailable or for high-quality conversations:

| Setting | Value |
|---|---|
| Model | Claude 3.5 Sonnet |
| Rate Limit | `ADVISOR_RATE_LIMIT` (default: `10/minute`) |
| Key | `ANTHROPIC_API_KEY` |

### Used For
- AI Advisor conversations (SSE streaming)
- Complex multi-step reasoning
- Fallback for local LLM failures

## Layer 4: Graceful Degradation

**No endpoint ever returns a 500 due to AI unavailability.** When all AI layers fail:
- Auto-categorizer returns `"Other"` with low confidence
- Insights returns empty array
- Advisor returns "AI unavailable" message
- Receipt OCR returns error details

## AI Services

### Auto-Categorizer (`services/auto_categorizer.py`)

```
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

### Receipt OCR (`services/receipt_ocr.py`)

Uses multimodal vision model (Llava-compatible):
1. Accepts base64 image
2. Extracts: merchant, amount, date, items, category
3. Returns structured `ReceiptResult` schema

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

| Variable | Required | Default | Impact |
|---|---|---|---|
| `LLAMA_ENABLED` | No | `false` | Enables local AI |
| `LLAMA_SERVER_URL` | No | `http://127.0.0.1:8080` | llama.cpp endpoint |
| `ANTHROPIC_API_KEY` | No | — | Enables cloud AI |
| `ADVISOR_RATE_LIMIT` | No | `10/minute` | Cloud AI throttle |

**Minimum viable setup:** No AI configured. The app works fully with rule-based features only.
