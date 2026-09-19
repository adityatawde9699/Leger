# Ledger improvement roadmap

## Product direction

Ledger should become a calm, trustworthy personal finance coach for ordinary people—not a dashboard full of charts or an AI chatbot that restates transactions.

The core promise should be:

> “Ledger helps me understand where my money is going, decide what to do next, and follow through—using evidence from my own data.”

The product should work for a first-time budgeter, a power user importing bank statements, and an Indian user managing UPI, cash, credit, investments, GST receipts, and irregular income. The app should feel useful with zero AI configuration and become more helpful—not merely more verbose—when AI is enabled.

This roadmap is based on the current implementation in `frontend/src`, `backend/app/main.py`, `backend/app/models.py`, and `backend/app/services`. It favors trust, data quality, and decision support before adding more surface area.

## Current state: strengths and gaps

### What is already valuable

- A broad foundation exists: transactions, accounts, budgets, statement/SMS imports, recurring payments, investments, analytics, exports, audit logs, PWA support, and Google/dev auth.
- The backend already separates deterministic services from AI services. Categorization, GST, budget math, anomaly detection, forecasts, and portfolio metrics can run without an LLM.
- There is meaningful grounding work in `services/insights.py`: the advisor receives period totals, budgets, merchants, recurring payments, monthly breakdowns, anomalies, forecasts, and recent transactions.
- User corrections are persisted in `CategoryCorrection`, which is the right foundation for personalized categorization.
- The UI has good utility primitives: quick add, command palette, import flows, responsive navigation, loading states, and a production PWA build.

### The main problems to solve

1. **Data is not yet a sufficiently trustworthy source of truth.** Account balances, statement balances, cash, transfers, pending items, duplicates, and investment values are represented unevenly. Advice can be numerically correct against an incomplete or incorrectly classified ledger while still being wrong for the person.
2. **The product is wide before it is deep.** The app has 10+ destinations and many advanced features, but the first-run path—connect/import, clean up, understand, choose a goal, act—is not yet the central experience.
3. **AI output is not consistently evidence-bearing.** `proactive_insights.py` asks for exactly 5–7 insights and accepts valid-looking JSON, but it does not require an evidence reference, calculation, confidence, or an action outcome. This creates a risk of plausible filler.
4. **Insight quality is limited by simplistic baselines.** Forecasting uses category-level EWMA with a minimum month threshold; anomaly detection uses global/category heuristics; recurring detection groups raw descriptions. These are useful starts, but they need data sufficiency checks, seasonality awareness, and user feedback.
5. **Import reliability is product-critical but underdeveloped.** Statement processing uses `asyncio.create_task()` with a request-created SQLAlchemy session and is explicitly marked “Celery in Phase 2.” A crash or multi-worker deployment can lose or strand jobs.
6. **The AI contract is unclear to users.** Deterministic answers, cached answers, cloud-provider answers, and uncertainty are not visibly distinguished. Privacy, retention, and “why am I seeing this?” controls need to be first-class.
7. **Verification needs strengthening.** `npm run build` passes. Backend tests are present, but `pytest` is not installed in the current environment, so CI/test health should be treated as unverified until dependencies are installed and executed.

## Product principles

- **Evidence before eloquence.** Every recommendation must point to the transactions, period, budget, rule, or user goal behind it.
- **No insight is better than a weak insight.** The system may return “not enough data” or “nothing notable” instead of manufacturing a quota of cards.
- **Separate facts, interpretations, and actions.** A user should be able to distinguish “you spent ₹X” from “this is unusual” from “try doing Y.”
- **User control over automation.** Imports, categorization, corrections, recurring payments, and AI suggestions must be reviewable and reversible.
- **Progress over perfection.** A user should get value after adding one account and a few transactions, without needing to configure every feature.
- **Inclusive defaults.** Support INR and other currencies, cash and bank accounts, irregular income, shared household situations, low financial literacy, mobile screens, and users who do not want to connect a bank.
- **Privacy is a product feature.** Minimize data sent to models, disclose provider usage, allow deletion/export, and make cloud AI opt-in or clearly configurable.

## North-star user loop

```text
Capture money movement → confirm/repair data → understand baseline → choose a goal
        ↑                                                        ↓
        └────────────── review progress ← take one small action ──┘
```

The roadmap should improve this loop before expanding into additional financial products.

## Phased plan

### Phase 0 — Establish truth and release safety (1–2 weeks)

**Outcome:** The team knows what the app can safely claim, and every future change can be measured.

- Create a product data dictionary: transaction types, transfer semantics, source values, account balance meaning, sign conventions, currency rules, date/time rules, and investment valuation rules.
- Add a `data_quality` layer to every analytics response: coverage dates, number of transactions, number of uncategorized items, number of duplicate suspects, income confidence, and whether account balances are stale/manual.
- Add a visible “last updated / based on” period to dashboard cards and AI responses.
- Fix documentation drift between `docs/architecture/001-hybrid-ai-architecture.md`, `docs/wiki/AI-System.md`, and the actual `ai_router.py` provider chain. Document the actual production decision and privacy implications.
- Install backend test dependencies in CI/dev instructions and run the existing suite. Add a frontend lint/type-check/test strategy; a successful Vite build alone is not enough.
- Add structured telemetry without storing raw financial text: latency, provider, fallback, parse success, evidence validation, user dismissal, correction, and action completion.
- Define a small release checklist for financial calculations: decimal arithmetic, date range, timezone, currency, empty data, duplicate data, and incomplete history.

**Exit criteria**

- Every summary/forecast/insight can state its date range and data sufficiency.
- CI runs backend tests and frontend build checks on every change.
- No documentation claims a privacy or AI behavior that the code does not implement.

### Phase 1 — Make the ledger dependable (2–4 weeks)

**Outcome:** Users can trust that their financial history is complete, deduplicated, and understandable.

- Add transaction semantics for `transfer`, `refund`, `reimbursement`, `pending`, and `excluded`; do not force all money movement into income/expense.
- Add explicit import review before commit: preview rows, detected columns, account mapping, inferred type, duplicate matches, category confidence, and “accept all / review uncertain” controls.
- Replace the in-process `asyncio.create_task()` import path with a durable job mechanism (initially a database-backed worker is sufficient; Redis/Celery can follow). Reopen a fresh DB session inside the worker, support retries, progress, cancellation, and idempotency.
- Store an import fingerprint and statement/account identity so re-uploading the same file is safe while legitimate same-amount transactions are not incorrectly discarded.
- Improve merchant normalization with a user-visible canonical merchant and original description. Let users merge/split merchant aliases.
- Add bulk edit, undo, multi-select, and a clear correction flow for category, type, account, date, and transfer matching.
- Add account reconciliation: expected balance, imported statement balance, difference, last reconciliation date, and a guided fix list.
- Add recurring transaction records with cadence, amount range, next expected date, confidence, active/paused/cancelled state, and user confirmation. Do not infer subscriptions from “same description twice” alone.
- Make category taxonomy configurable enough for personal/household use while keeping stable reporting groups underneath.

**Exit criteria**

- A user can import a statement, review uncertain rows, confirm it, and safely repeat the import.
- Transfers/refunds do not inflate income or expenses.
- Dashboard balance and imported statement balance can be reconciled with an explainable difference.

### Phase 2 — Create a much better first-run and daily experience (3–5 weeks)

**Outcome:** A new user reaches a useful personal baseline in minutes and knows what to do next.

- Replace the feature-first first run with a short setup: currency/region, income pattern, starting balances, one account or import, and one goal.
- Give the dashboard a “Today / This month / Next action” hierarchy:
  - cash available and upcoming obligations;
  - income, committed spend, flexible spend, and remaining safe-to-spend amount;
  - one or two high-confidence observations;
  - a single recommended action with a completion button.
- Add an empty-state path for no data, partial data, irregular income, and no budgets. Never show a “health score” without explaining that it is provisional.
- Add a lightweight goal model: emergency fund, debt payoff, spending reduction, savings target, or custom goal. Track target, deadline, current progress, and next contribution.
- Redesign budgets around decisions: suggested baseline, user target, remaining amount, pace, and what to change—not only a red/green percentage.
- Add “safe to spend” only after committed bills, budgeted obligations, upcoming recurring payments, and data freshness are known. Label it as an estimate, never as a bank balance.
- Improve mobile quick capture: amount-first entry, merchant/category suggestions, receipt attachment, split transaction, recurring toggle, and offline queue with sync status.
- Consolidate navigation around Home, Activity, Plans, Goals, and Ask Ledger. Put advanced areas such as GST, audit, benchmarks, and portfolio diagnostics under a deliberate “More” area.
- Add accessibility work: keyboard support, focus management for sheets/dialogues, screen-reader labels, color-independent status, reduced motion, and readable contrast.

**Exit criteria**

- A new user can add/import data and receive one useful, explainable next action without visiting multiple advanced screens.
- Every important empty state explains what is missing and how to fix it.
- The dashboard answers “Where am I?”, “What changed?”, and “What should I do next?” in under a minute.

### Phase 3 — Build evidence-based analysis (4–6 weeks)

**Outcome:** Analysis is genuinely insightful, not a list of generic observations.

#### A shared analysis engine

Create a canonical analysis object consumed by Dashboard, Analytics, Proactive Insights, and Advisor:

```json
{
  "id": "spending.food.increase_30d",
  "kind": "trend",
  "claim": "Food spending is 28% higher than your prior 30-day baseline",
  "evidence": {
    "period": "2026-08-22/2026-09-20",
    "comparison_period": "2026-07-23/2026-08-21",
    "amount": 8420,
    "comparison_amount": 6578,
    "transaction_ids": ["..."],
    "method": "same-length-period comparison"
  },
  "confidence": "medium",
  "data_quality": {"months": 3, "coverage": 0.91},
  "recommended_action": "Review the three largest food merchants",
  "action_type": "open_transactions",
  "status": "new"
}
```

Implement the following analyses in order:

- **Period comparisons:** same-length periods, month-over-month, rolling 30/90 days, and year-over-year where enough history exists. Avoid comparing a partial current month with a full prior month without normalization.
- **Fixed vs flexible spending:** identify recurring/committed obligations separately from discretionary categories.
- **Cash-flow runway:** forecast near-term balance using income cadence, confirmed recurring payments, and account balances; show a range when income is irregular.
- **Budget pacing:** compare actual daily pace with remaining days and historical pace, not only month-end extrapolation.
- **Merchant and subscription leakage:** detect price increases, duplicate services, dormant recurring payments, and concentration risk, each with supporting transactions.
- **Anomalies with explanations:** use personal baseline, category baseline, merchant history, amount, date, and duplicate similarity; include false-positive feedback.
- **Goal scenarios:** “If I reduce eating out by ₹X,” “Can I afford this purchase?”, and “What happens if income is 20% lower?” Use deterministic scenario math first.
- **Debt and credit readiness:** only provide credit-related guidance when actual credit account/limit/payment data exists. Do not label a proxy score as a bureau score.
- **Investment analysis:** clearly separate user-entered prices from live prices, mark stale valuations, and avoid investment recommendations without risk profile, holdings quality, and current market data.

Each analysis should have a minimum sample/history requirement and return `insufficient_data` instead of a confident result.

**Exit criteria**

- Every insight has evidence, comparison window, calculation method, data sufficiency, and a linked action.
- A user can dismiss, correct, snooze, or mark an insight useful; the system learns which classes are helpful.
- Generic outputs such as “review your spending” are rejected unless they include a quantified reason and an actionable target.

### Phase 4 — Make AI a grounded copilot (4–6 weeks)

**Outcome:** AI helps the user reason and act, while calculations and permissions remain deterministic.

#### AI should do

- Translate a user question into a structured query over the analysis engine.
- Explain a detected pattern in plain language.
- Compare options using explicit assumptions.
- Suggest a small number of actions tied to existing UI flows.
- Ask a clarifying question when the user’s goal or data is ambiguous.
- Summarize an import or monthly review, with links to the underlying rows.

#### AI should not do

- Invent transactions, balances, benchmarks, market data, or tax conclusions.
- Decide category, transfer, deletion, budget, or investment actions without confirmation.
- Give a fixed number of insights simply to fill a screen.
- Present a proxy score as a regulated or institution-issued score.
- Use cloud AI silently for sensitive data.

#### Implementation plan

- Introduce tool-like server functions for facts: `get_summary`, `compare_periods`, `list_evidence`, `get_recurring`, `simulate_goal`, `open_transactions`. The model chooses which function to call; Python performs the calculation.
- Return a structured advisor response: `answer`, `facts`, `assumptions`, `uncertainties`, `suggested_actions`, and `source_links`.
- Ground every generated claim against the analysis object. Reject or rewrite claims whose amounts, periods, categories, or transaction IDs are not present in evidence.
- Add an answer mode selector: “quick answer,” “show the math,” and “plan with me.”
- Add conversation memory only for explicit user preferences/goals, not unrestricted financial history. Recompute facts at request time.
- Show “calculated by Ledger” versus “explained by AI,” provider/privacy status, and the data range used.
- Add AI feedback that is more useful than thumbs up/down: inaccurate number, irrelevant, too generic, unsafe, helpful, completed action.
- Prefer deterministic responses for direct factual questions such as latest transaction, totals, budget remaining, and period comparisons. Use the LLM for explanation and planning.
- Add prompt/evaluation fixtures with adversarial questions, missing data, contradictory imports, prompt injection in merchant descriptions, and currency/date edge cases.

**Exit criteria**

- In an evaluation set, factual answers have zero unsupported numbers and high evidence-link coverage.
- AI can turn a recommendation into a confirmed UI action, and the action is auditable.
- When data is insufficient, the assistant explains exactly what would improve the answer.

### Phase 5 — Personalization, privacy, and resilience (ongoing)

**Outcome:** Ledger feels personal without becoming invasive or fragile.

- Add per-user preferences: categories, merchant aliases, pay cycle, recurring tolerance, risk comfort, household/shared expenses, and insight frequency.
- Add privacy controls: provider opt-in, cloud-data notice, retention period, delete conversations, delete account/data, export all data, and redact sensitive fields before AI calls.
- Make AI provider routing observable and safe: per-task provider policy, cost/latency budgets, circuit breakers, timeout limits, retry caps, and no accidental fallback to an unapproved provider.
- Move TTL caches to a shared cache for multi-worker deployments and invalidate by data version, not only wall-clock time.
- Add background jobs for recurring detection, insight generation, statement processing, and notification delivery.
- Add notification preferences with quiet hours and a strict cap on proactive messages.
- Support encrypted backups and restore testing before marketing “local-first” or “privacy-first” as a primary promise.

## AI quality contract

Every AI-generated or AI-explained output should pass these checks before reaching the UI:

1. **Grounding:** every numeric/entity claim maps to a current fact or evidence record.
2. **Temporal correctness:** comparison periods are equal or the difference is disclosed.
3. **Data sufficiency:** history, coverage, and category confidence meet the analysis threshold.
4. **Uncertainty:** confidence is shown when the conclusion is probabilistic.
5. **Actionability:** the user gets one concrete next step, or a clear reason no action is recommended.
6. **Safety:** tax, credit, and investment guidance is framed appropriately and escalated to professional advice where needed.
7. **User control:** no mutation happens without confirmation; all changes are undoable and logged.

The product should prefer three excellent insights over seven mediocre ones. A good insight has this shape:

> “Food spending is ₹1,842 higher than your previous 30 days, mostly from three Swiggy transactions. If you cap the next two weeks at ₹1,500, you would likely finish near your usual range. Review transactions.”

It states what changed, why the system believes it, and what the user can do.

## Metrics that matter

### User outcomes

- Time from signup to first trusted import/transaction.
- Percentage of active users with reconciled accounts and categorized transactions.
- Weekly users who complete a recommended action.
- Reduction in uncategorized/duplicate/unreviewed transactions.
- Goal progress and retention after 30/90 days.

### Insight quality

- Evidence coverage: percentage of claims with valid evidence links.
- Unsupported-number rate: target zero for released flows.
- Insight usefulness, dismissal, snooze, and correction rates by insight type.
- Action conversion: insight viewed → evidence opened → action completed.
- False-positive rate for anomalies, recurring payments, and budget warnings.

### Reliability and trust

- Import success, retry, duplicate prevention, and reconciliation rates.
- P95 API and AI latency, provider fallback rate, timeout/error rate, and cost per active user.
- Crash-free sessions, offline sync success, and background-job recovery.
- Data export/delete completion and privacy-control usage.

## Recommended build order

If capacity is limited, build in this order:

1. Data dictionary, test/CI baseline, and data-quality metadata.
2. Reliable import review, deduplication, transfer/refund semantics, and reconciliation.
3. A simpler first-run flow plus a dashboard focused on cash flow and next action.
4. Shared evidence-based analysis objects and better period comparisons.
5. Grounded advisor/tool calls and evidence-linked proactive insights.
6. Goals, scenarios, personalization, notifications, and advanced investment/credit analysis.

Do not prioritize another AI provider, more dashboard cards, or a new financial feature until the current system can explain where a number came from and whether the user’s underlying data is complete.

## Definition of “done” for the personal finance experience

Ledger is ready for a broad user audience when a new user can:

- add or import accounts safely;
- understand what data is missing or uncertain;
- see a trustworthy current cash-flow picture;
- set one realistic goal;
- receive a small number of quantified, evidence-linked insights;
- ask a question and see the math and source rows;
- confirm or reject every suggested change;
- take an action and see its effect over time;
- export or delete their data;
- use the core experience without an AI API key.

