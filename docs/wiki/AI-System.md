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

### User privacy control

Cloud explanations are controlled per user from Profile. The `cloud_ai_enabled` preference is enabled by default for backward-compatible behavior and can be disabled at any time. Disabled users still receive deterministic factual answers and rule-based proactive insights; Ledger does not call the cloud AI router for those paths. When enabled, the UI discloses that minimized financial context may be sent to a configured provider. Provider retention policy is deployment-configured and surfaced as unknown when no contractual value is supplied; local conversation retention and broad identifier redaction are enforced before provider calls.

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

Direct factual advisor questions are routed through `backend/app/services/advisor_facts.py` before any model call. Ledger performs the arithmetic and returns a versioned `advisor.v1` response contract containing facts, evidence, assumptions, uncertainties, suggested actions, data-only source links, and explicit calculation/explanation/privacy provenance; the UI labels the response “Calculated by Ledger.” Open-ended interpretation and planning remain AI-assisted and are labeled “Explained by AI,” with the data range and cloud-AI state visible to the user.

The Advisor supports three explicit modes: `quick` for a concise answer, `math` for facts and calculation assumptions, and `plan` for a small set of reversible next steps. The mode changes presentation guidance only; it never authorizes a model or UI action to mutate financial data.

Prompt-safety fixtures cover common injection phrases, hostile merchant-like text, context/question separation, currency preservation, oversized input, date boundaries, contradictory import inference versus user review, and structured-response violations. These are guard tests, not proof that an external model is trustworthy.

Before an open-ended advisor reply is cached or persisted, Ledger checks explicit currency-coded monetary claims, dates, transaction IDs, and explicitly labeled merchant/category claims against the current financial context. Unsupported claims or currency codes are replaced with a verification warning; deterministic factual answers bypass the model entirely. The entity check is intentionally conservative and does not pretend to validate every noun in free-form prose.

The advisor context includes a machine-readable, Ledger-calculated facts block with totals, category totals, equal-length comparison values, evidence IDs, currency, period, and data-quality warnings. It also includes deterministic fact-tool results (`get_summary`, `compare_periods`, `list_evidence`, `get_recurring`, and budget/evidence navigation results). For open-ended questions, the model may request one allowlisted read-only tool, including a bounded `simulate_goal`; Python validates the tool and arguments against the current user's data before returning the result. Transaction descriptions remain untrusted data and are not treated as instructions. Mutation tools remain out of scope.

Open-ended Advisor replies must be JSON `advisor.v1` responses containing an answer, evidence-linked claims, assumptions, uncertainties, and bounded review actions. Every factual claim must cite current-user transaction IDs; Ledger validates the answer and claims for unsupported amounts, dates, IDs, currencies, and explicitly labeled merchant/category entities. Invalid or non-JSON model output is withheld and replaced with a verification message before persistence or caching.

Provider routing is bounded by `AI_PROVIDER_MAX_ATTEMPTS` and `AI_PROVIDER_TIMEOUT_SECONDS`. Deployments can set `AI_PROVIDER_ALLOWLIST` or `AI_TASK_PROVIDER_POLICY` (a JSON map such as `{"advisor":["Groq"],"insights":["Cerebras"]}`) to prevent a task from falling back to an unapproved provider. Invalid task policy JSON fails closed for that task rather than silently widening the provider set. Each worker also opens a process-local circuit after `AI_PROVIDER_CIRCUIT_FAILURE_THRESHOLD` failures and probes the provider again after `AI_PROVIDER_CIRCUIT_COOLDOWN_SECONDS`. `GET /ai/provider-health` exposes only configured/allowed state, circuit state, counters, and latency; it never exposes credentials or raw provider errors. Deployment-wide health and cost budgets remain infrastructure work.

Advisor, anomaly, forecast, and proactive-insight cache keys include a database-visible per-user audit version. The cache uses optional Redis as an L2 shared read-through/write-through store for multi-worker deployments, with the process-local TTL cache as a fail-open fallback when Redis is unavailable. User-scoped invalidation clears both layers; TTL remains an additional expiry safeguard.

AI-bound advisor text redacts common email, phone, tax-identifier, and long account-identifier patterns before provider calls. Conversation records are retained for the configured `AI_CONVERSATION_RETENTION_DAYS` (default 90) and expired threads are purged when conversation data is accessed; users can also delete a thread immediately.

Conversation continuity sent to a provider is limited to the last few explicit user preference/goal statements. Prior financial questions and assistant prose are retained only for the user's conversation view and are not replayed as unrestricted model memory; current financial facts are recomputed per request.

Proactive insight frequency is user-controlled: `off` suppresses the endpoint, `important` filters to priority 4–5, and `daily`/`weekly` preserve the full available set while scheduled delivery remains unimplemented.

When a user has no transactions, the advisor returns a deterministic setup response and does not call a cloud provider. It explains that personalized analysis requires imported or manually entered history.

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

### Financial picture (`services/credit_health.py`)

The legacy `/credit-health` route now returns only posted-transaction income, net spending, cash flow, a calculated savings rate when income exists, the covered period, and data-quality warnings. It does **not** issue a 300–900 score or claim to assess creditworthiness: Ledger lacks verified credit limits, repayment history, and bureau data. A currency mismatch suppresses combined amounts. The legacy `/benchmarks` route likewise returns a personal spending breakdown with an explicit unavailable peer-comparison status; Ledger has no verified representative peer dataset.

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
