# ADR 001: Hybrid AI Architecture (Local + Cloud Fallback)

**Status:** Accepted  
**Date:** 2026-05-16  
**Decision Makers:** Core Team  

## Context

Ledger requires AI capabilities across multiple services:
- **Transaction auto-categorization** — classify descriptions into spending categories
- **Proactive financial insights** — detect trends, budget overruns, anomalies
- **AI advisor chat** — conversational financial guidance with SSE streaming
- **Receipt OCR** — extract structured data from receipt images (multimodal)
- **Bill negotiation** — analyze recurring payments and generate negotiation strategies

The system serves price-sensitive Indian users on variable hardware. Key constraints:
1. **Latency**: Categorization must be <500ms for interactive UX
2. **Cost**: Cloud API calls at scale ($0.003–$0.015/1K tokens) are unsustainable for a freemium model
3. **Privacy**: Financial data should not leave the user's infrastructure by default
4. **Availability**: The app must function when cloud APIs are rate-limited or unavailable

## Decision

We adopt a **hybrid AI routing architecture** with the following priority chain:

```
Request → Rule Engine → Local LLM (llama.cpp) → Cloud LLM (Anthropic) → Graceful Fallback
```

### Layer 1: Rule Engine (Zero Latency)
- Keyword/regex-based categorization handles ~70% of Indian transaction descriptions
- GST rate mapping is fully deterministic (no AI needed)
- Budget threshold alerts are computed mathematically

### Layer 2: Local LLM via llama.cpp (Low Latency, Zero Cost)
- Served via `llama.cpp` HTTP server on `http://127.0.0.1:8080`
- Models: Mistral 7B Q4 for text, Llava 1.6 for vision (receipt OCR)
- JSON-constrained output via system prompts to avoid parsing failures
- Toggle: `LLAMA_ENABLED=true` + `LLAMA_SERVER_URL`

### Layer 3: Cloud LLM via Anthropic (High Quality, Pay-per-use)
- Claude 3.5 Sonnet for complex advisor conversations
- Used only when local LLM is unavailable or confidence is low
- API key: `ANTHROPIC_API_KEY`
- Rate-limited to prevent cost spikes (`ADVISOR_RATE_LIMIT=10/minute`)

### Layer 4: Graceful Degradation
- If all AI layers fail, the system returns rule-based results or informative empty states
- No endpoint returns a 500 due to AI unavailability
- All AI features are optional — the app is fully functional without any LLM

## Implementation

### AI Router (`services/ai_router.py`)
```python
class AIRouter:
    async def generate(system, user_message, temperature=0.3):
        # 1. Try llama.cpp
        # 2. Fallback to Anthropic
        # 3. Return None (caller handles gracefully)
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
| `LLAMA_ENABLED` | No | `false` | Enable local llama.cpp |
| `LLAMA_SERVER_URL` | No | `http://127.0.0.1:8080` | llama.cpp server URL |
| `ANTHROPIC_API_KEY` | No | `None` | Anthropic API key |
| `ADVISOR_RATE_LIMIT` | No | `10/minute` | Rate limit for advisor |

## Consequences

### Positive
- **Zero marginal cost** for 90%+ of AI operations (rules + local LLM)
- **Sub-100ms latency** for rule-based operations
- **Full offline capability** with llama.cpp
- **No vendor lock-in** — Anthropic is swappable for any OpenAI-compatible API
- **Privacy by default** — data stays local unless cloud fallback is explicitly enabled

### Negative
- **Hardware requirements**: llama.cpp needs ~6GB VRAM for 7B model + vision
- **Model quality**: Local 7B models are less capable than Claude 3.5 for complex reasoning
- **Operational complexity**: Two inference stacks to maintain (local + cloud)

### Risks
- Local model quality may degrade for non-English or mixed-language descriptions
- Anthropic API pricing or terms may change, requiring provider switch
- Vision model (Llava) accuracy on low-quality receipt photos is unproven at scale

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Cloud-only (Anthropic/OpenAI) | Too expensive at scale, privacy concerns |
| Local-only (llama.cpp) | Insufficient quality for advisor conversations |
| Ollama instead of llama.cpp | Heavier runtime, less control over serving |
| Fine-tuned model | Training data insufficient, maintenance burden |
| No AI (rules only) | Insufficient for advisor, OCR, and negotiation features |
