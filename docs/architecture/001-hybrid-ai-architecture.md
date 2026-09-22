# ADR 001: Hybrid AI Architecture (Deterministic + Cloud Fallback)

**Status:** Accepted  
**Date:** 2026-05-16  
**Decision Makers:** Core Team  

## Context

Ledger has optional AI capabilities across multiple services:
- **Transaction auto-categorization** — classify descriptions into spending categories
- **Proactive financial insights** — detect trends, budget overruns, anomalies
- **AI advisor chat** — conversational financial guidance with SSE streaming
- **Receipt OCR** — extract structured data from receipt images
- **Bill negotiation** — analyze recurring payments and generate negotiation strategies

The system serves price-sensitive Indian users on variable hardware. Key constraints:
1. **Latency**: Categorization must be <500ms for interactive UX
2. **Cost**: Cloud API calls at scale ($0.003–$0.015/1K tokens) are unsustainable for a freemium model
3. **Privacy**: Deterministic features should not require a provider; cloud AI must be explicit and disclosed
4. **Availability**: The app must function when cloud APIs are rate-limited or unavailable

## Decision

We adopt a **Tiered Intelligent Extraction architecture** with the following priority chain:

```
Request → Rule Engine/Deterministic calculation → Configured cloud provider router → Graceful Fallback
```

### Layer 1: Rule Engine (Zero Latency)
- Keyword/regex-based categorization handles ~70% of Indian transaction descriptions
- GST rate mapping is fully deterministic (no AI needed)
- Budget threshold alerts are computed mathematically

### Layer 2: Configured cloud providers
- The implemented router tries Groq, Cerebras, Gemini, Cohere, then OpenRouter when credentials are configured.
- Direct factual advisor questions bypass the router and use deterministic Ledger calculations.
- The advisor exposes configured provider names without exposing credentials.
- Rate limits protect provider quota (`ADVISOR_RATE_LIMIT=10/minute`).

### Layer 4: Graceful Degradation
- If all AI layers fail, the system returns rule-based results or informative empty states
- No endpoint returns a 500 due to AI unavailability
- All AI features are optional — the app is fully functional without any LLM

## Implementation

### AI Router (`services/ai_router.py`)
```python
class AIRouter:
    async def generate(system, user_message, task_type="default"):
        # Try configured providers in order; caller handles total failure.
```

### Service Pattern
Each AI service follows the same pattern:
1. Attempt rule-based computation
2. If rules produce low-confidence or "Other" result, call `ai_router.generate()`
3. Parse JSON response with validation
4. On any failure, return rule-based result

### Configuration
| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | No | `None` | Primary cloud provider |
| `CEREBRAS_API_KEY` | No | `None` | Cloud fallback provider |
| `GEMINI_API_KEY` | No | `None` | Cloud fallback provider |
| `COHERE_API_KEY` | No | `None` | Cloud fallback provider |
| `OPENROUTER_API_KEY` | No | `None` | Final cloud fallback provider |
| `ADVISOR_RATE_LIMIT` | No | `10/minute` | Rate limit for advisor |

## Consequences

### Positive
- **Zero marginal cost** for deterministic operations; cloud AI is optional
- **Sub-100ms latency** for rule-based operations
- **Core offline capability** — the ledger and direct factual calculations work without an AI provider
- **No vendor lock-in** — providers are swappable through the router
- **Provider transparency** — cloud configuration is disclosed instead of being implied to be local

### Negative
- **Privacy tradeoff**: open-ended AI requests may send financial context to a configured cloud provider.
- **Provider dependency**: open-ended explanations depend on provider availability and keys.
- **Model quality**: deterministic calculations are reliable, but open-ended explanations vary by provider.

### Risks
- Cloud provider availability, pricing, and terms may change, requiring provider review
- PaddleOCR accuracy on low-quality receipt photos requires validation

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Cloud-only provider | Privacy and cost concerns; deterministic core remains provider-free |
| Local-only provider | Not part of the current deployed router |
| Ollama/local server | Requires a separate deployment contract not present in the current code |
| Fine-tuned model | Training data insufficient, maintenance burden |
| No AI (rules only) | Insufficient for advisor, OCR, and negotiation features |
