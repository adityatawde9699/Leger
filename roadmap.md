# Ledger improvement roadmap

## Product direction

Ledger should become a calm, trustworthy personal finance coach for ordinary people—not a dashboard full of charts or an AI chatbot that restates transactions.

The core promise should be:

> “Ledger helps me understand where my money is going, decide what to do next, and follow through—using evidence from my own data.”

The product should work for a first-time budgeter, a power user importing bank statements, and an Indian user managing UPI, cash, credit, investments, GST receipts, and irregular income. The app should feel useful with zero AI configuration and become more helpful—not merely more verbose—when AI is enabled.

This roadmap is based on the current implementation in `frontend/src`, `backend/app/main.py`, `backend/app/models.py`, and `backend/app/services`. It favors trust, data quality, and decision support before adding more surface area.

## Implementation status

Status reviewed: 2026-09-23. Completed items below are limited to behavior present in the current codebase and covered by the verification snapshot.

The first roadmap slice is now implemented: proactive insights expose evidence, confidence, source, action, and data-quality metadata; unsupported model insights are rejected; summary responses expose coverage warnings; the dashboard makes analytical limitations visible; statement imports can be previewed before commit, can be assigned to a user-owned account, use a database-backed payload with startup recovery and duplicate-claim protection, and support retrying failed jobs; the ledger distinguishes expenses, refunds, and transfers in core entry, filtering, balance, and summary flows; manual transactions enforce account ownership; account balances can be explicitly reconciled with an observed bank/wallet balance and audited; users can create and track savings, emergency-fund, debt, and custom goals with deadlines and progress; advisor streams now surface the period, coverage, and transaction count used for an answer; insight actions now navigate to the relevant activity view; and Analytics now includes an explainable scenario planner based on the user's recent history.
Privacy controls now include a full portable data export and an explicit, confirmation-gated permanent deletion flow exposed in Profile.
Backend development dependencies are now declared separately and GitHub Actions runs backend lint/tests plus the frontend production build on pushes and pull requests.
Phase 0 release safety is now documented in `docs/RELEASE-CHECKLIST.md`, and the frontend quality strategy is documented in `frontend/QUALITY.md`.
Privacy-safe structured telemetry now records operational latency, provider/fallback, parse success, evidence validation, feedback, correction, and import/insight outcomes without raw financial text.
Budgets now include active custom expense categories, preserve existing category budgets across taxonomy changes, accept history-based suggestions for custom categories, and show remaining daily allowance plus a clearly labeled month-end pace estimate.
The Dashboard now selects one data-aware next step from account setup, failed imports, pending or uncategorized transactions, stale/unassigned accounts, missing budgets, or missing goals; its transaction review actions open the matching Activity filter. The Docker entrypoint now passes migration Python through a quoted heredoc, avoiding shell parsing of embedded SQL quotes, and CI tests both shell and embedded Python syntax.
Shared data-quality metadata now also reports conservative exact-match duplicate suspects and warns users before analysis is treated as complete.
Direct factual advisor questions now use deterministic Ledger arithmetic with evidence transaction IDs and assumptions; open-ended questions remain AI-assisted and are visibly labeled in the chat UI.
Statement imports now persist a content fingerprint for idempotent re-uploads, while transaction row fingerprints include account and type so legitimate same-value transactions across accounts are preserved.
The Dashboard now lists pending/processing/failed statement jobs and lets users retry failed jobs without leaving the main workflow.
Recurring detection now exposes cadence, amount range, confidence, active/stale status, and evidence instead of treating two matching descriptions as confirmed subscriptions.
The Dashboard now has a first-run setup state based on all-time history, with direct actions to add/import data, set up an account, or create a first goal.
AI/provider documentation now matches the implemented router, and advisor metadata discloses configured cloud providers without exposing credentials.
Added `docs/wiki/Data-Dictionary.md` to make transaction semantics, balance meaning, import identity, currency behavior, and analysis conventions explicit.
Summary responses now include a versioned shared analysis object with period, quality, calculation method, and transaction evidence IDs for total and category claims.
Analytics now has a canonical equal-length period comparison (`/analytics/compare`) that returns current/prior windows, category deltas, evidence transaction IDs, and an explicit `insufficient_data` state; the Analytics view surfaces the comparison without asking AI to calculate it.
Proactive insights now have stable non-sensitive IDs and auditable feedback (`helpful`, `inaccurate`, `irrelevant`, `too_generic`, `unsafe`, `completed_action`, `dismissed`, or `snoozed`) stored through the audit trail; the dashboard exposes lightweight usefulness controls.
Transactions now carry explicit `status` (`posted`, `pending`, or `excluded`) and a distinct `reimbursement` type. Pending/excluded rows remain reviewable and exportable but do not affect committed balances, summaries, forecasts, budgets, scenarios, or AI facts; migration, Quick Add, Activity filters, and data-quality warnings are included.
Activity now provides bulk confirmation/exclusion controls, so pending rows can be repaired without deleting their audit history.
Transaction updates now record before/after snapshots and expose a one-step undo endpoint; Activity offers an undo action after bulk category/status corrections.
Import jobs now expose durable row progress and cooperative cancellation; the Dashboard polls active jobs, shows progress, and supports cancel/retry without losing the stored payload.
Import review now shows AI category confidence and stable row identities, and lets users exclude uncertain rows before the durable job is created.
Phase 1 personalization is now implemented: merchant aliases apply across manual, edited, and statement-imported transactions while retaining the original description; custom categories are user-scoped and preserve stable built-in reporting groups; and recurring candidates can be explicitly confirmed into evidence-linked active, paused, or cancelled rules. Profile and Quick Add expose the personalization controls, while Dashboard confirmation keeps detection separate from commitment.

Verification snapshot: the complete backend suite passes in the CI-targeted Python 3.12 environment with Starlette's supported `httpx2` test client (59 passed, 1 skipped), Ruff passes, the frontend production build passes, and `git diff --check` passes.

The remaining unchecked items below are still planned work; completed items are marked `[x]` in their phase.

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
3. **AI output still needs a stronger shared fact/tool contract.** Proactive insights now require valid evidence references, confidence, and an action, but the advisor still relies primarily on a context prompt instead of a reusable calculation/tool layer. This limits structured “show me the math” answers.
4. **Insight quality is limited by simplistic baselines.** Forecasting uses category-level EWMA with a minimum month threshold; anomaly detection uses global/category heuristics; recurring detection groups raw descriptions. These are useful starts, but they need data sufficiency checks, seasonality awareness, and user feedback.
5. **Import review still needs depth.** Statement processing now uses a database-backed payload, fresh worker sessions, startup recovery, retry, duplicate-claim protection, content/row fingerprints, durable progress, cooperative cancellation, and pre-commit row exclusion. Merchant alias management and editable inferred fields remain open; ordinary transaction corrections now have an auditable one-step undo.
6. **The AI contract is unclear to users.** Deterministic answers, cached answers, cloud-provider answers, and uncertainty are not visibly distinguished. Privacy, retention, and “why am I seeing this?” controls need to be first-class.
7. **Verification needs strengthening.** The backend and frontend gates now execute successfully. Remaining verification debt is mostly framework deprecation cleanup (`on_event`, AnyIO compatibility warnings) and adding browser-level accessibility/user-flow tests beyond the production build.

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

**Status: Complete (2026-09-23).**

- [x] Create a product data dictionary: transaction types, transfer semantics, source values, account balance meaning, sign conventions, currency rules, date/time rules, and investment valuation rules.
- [x] Add a `data_quality` layer to every analytics response: coverage dates, number of transactions, number of uncategorized items, number of duplicate suspects, income confidence, and whether account balances are stale/manual.
- [x] Add a visible “last updated / based on” period to dashboard cards and AI responses.
- [x] Fix documentation drift between `docs/architecture/001-hybrid-ai-architecture.md`, `docs/wiki/AI-System.md`, and the actual `ai_router.py` provider chain. Document the actual production decision and privacy implications.
- [x] Install backend test dependencies in CI/dev instructions, run the backend suite, and add a GitHub Actions gate. Document the current frontend build/smoke-test strategy; browser interaction tests remain a later phase.
- [x] Add structured telemetry without storing raw financial text: latency, provider, fallback, parse success, evidence validation, user feedback, correction, and import/insight outcomes.
- [x] Define a release checklist for financial calculations: decimal arithmetic, date range, timezone, currency, empty data, duplicate data, and incomplete history.

**Exit criteria**

- [x] Every summary, forecast, anomaly response, proactive insight, and advisor response can state its date range and data sufficiency.
- [x] CI runs backend tests and frontend build checks on every change.
- [x] No documentation claims a privacy or AI behavior that the code does not implement.

### Phase 1 — Make the ledger dependable (2–4 weeks)

**Status: Complete (2026-09-23).**

**Outcome:** Users can trust that their financial history is complete, deduplicated, and understandable.

- [x] Add transaction semantics for `transfer`, `refund`, `reimbursement`, `pending`, and `excluded`; do not force all money movement into income/expense.
- [x] Add explicit import review before commit: preview rows, duplicate matches, category confidence, and row-level exclusion controls.
- [x] Extend the database-backed import worker with progress, cancellation, import fingerprints, and statement/account identity. The worker reopens a fresh DB session, recovers pending/stale jobs, supports retries, and protects against duplicate claims.
- [x] Store an import fingerprint and statement/account identity so re-uploading the same file is safe while legitimate same-amount transactions are not incorrectly discarded.
- [x] Improve merchant normalization with a user-visible canonical merchant and original description. User-scoped aliases can be created, updated, applied to existing/new/imported transactions, and removed; original descriptions remain intact.
- [x] Add bulk edit, one-step undo, multi-select, and a clear correction flow for category and status; type/account/date/transfer matching remains a follow-up editor.
- [x] Add account reconciliation: expected balance, imported statement balance, difference, last reconciliation date, and an audited correction flow.
- [x] Add recurring transaction records with cadence, amount range, next expected date, confidence, active/paused/cancelled state, and user confirmation. Detection remains a reviewable lead; confirmation stores posted-transaction evidence.
- [x] Make category taxonomy configurable enough for personal/household use while keeping stable reporting groups underneath. Built-in categories remain stable and users can add/deactivate personal categories.

**Exit criteria**

- [x] A user can import a statement, review uncertain rows, confirm it, and safely repeat the import.
- [x] Transfers/refunds do not inflate income or expenses.
- [x] Dashboard balance and imported statement balance can be reconciled with an explainable difference.
- [x] Merchant, category, and recurring changes are user-scoped, auditable, exportable, and covered by regression tests.

### Phase 2 — Create a much better first-run and daily experience (3–5 weeks)

**Outcome:** A new user reaches a useful personal baseline in minutes and knows what to do next.

- Replace the feature-first first run with a short setup: currency/region, income pattern, starting balances, one account or import, and one goal.
- Give the dashboard a “Today / This month / Next action” hierarchy:
  - cash available and upcoming obligations;
  - income, committed spend, flexible spend, and remaining safe-to-spend amount;
  - one or two high-confidence observations;
  - a single recommended action with a completion button.
- Add an empty-state path for no data, partial data, irregular income, and no budgets. Never show a “health score” without explaining that it is provisional. The Dashboard now handles no transactions, failed imports, pending/uncategorized rows, incomplete account linkage/reconciliation, and missing budgets/goals; explicit irregular-income and broader partial-history messaging remain open.
- [x] Add a lightweight goal model: emergency fund, debt payoff, spending reduction, savings target, or custom goal. Track target, deadline, and current progress; contribution guidance remains open.
- [x] Redesign budgets around decisions: history-based suggested baseline (including custom categories), user target, remaining amount, month-end pace estimate, and a remaining daily allowance—not only a red/green percentage.
- Add “safe to spend” only after committed bills, budgeted obligations, upcoming recurring payments, and data freshness are known. Label it as an estimate, never as a bank balance.
- Improve mobile quick capture: amount-first entry, merchant/category suggestions, receipt attachment, split transaction, recurring toggle, and offline queue with sync status.
- [x] Consolidate primary navigation around Home, Budgets, Goals, and Ask Ledger, with Activity and advanced areas under the secondary “More” navigation.
- Add accessibility work: keyboard support, focus management for sheets/dialogues, screen-reader labels, color-independent status, reduced motion, and readable contrast.

**Exit criteria**

- A new user can add/import data and receive one useful, explainable next action without visiting multiple advanced screens.
- Every important empty state explains what is missing and how to fix it.
- The dashboard answers “Where am I?”, “What changed?”, and “What should I do next?” in under a minute.

### Phase 3 — Build evidence-based analysis (4–6 weeks)

**Outcome:** Analysis is genuinely insightful, not a list of generic observations.

#### A shared analysis engine

- [x] Create a canonical analysis object consumed by Dashboard, Analytics, Proactive Insights, and Advisor:

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

- [x] **Period comparisons (initial slice):** equal-length configurable windows with current/prior totals, category deltas, evidence IDs, and `insufficient_data`. Month-over-month and year-over-year comparisons remain planned.
- **Fixed vs flexible spending:** identify recurring/committed obligations separately from discretionary categories.
- **Cash-flow runway:** forecast near-term balance using income cadence, confirmed recurring payments, and account balances; show a range when income is irregular.
- **Budget pacing:** compare actual daily pace with remaining days and historical pace, not only month-end extrapolation.
- **Merchant and subscription leakage:** detect price increases, duplicate services, dormant recurring payments, and concentration risk, each with supporting transactions.
- **Anomalies with explanations:** use personal baseline, category baseline, merchant history, amount, date, and duplicate similarity; include false-positive feedback.
- [x] **Goal scenarios (initial slice):** deterministic “reduce category,” “purchase affordability,” and “income shock” projections are available through Analytics; broader scenario coverage remains planned.
- **Debt and credit readiness:** only provide credit-related guidance when actual credit account/limit/payment data exists. Do not label a proxy score as a bureau score.
- **Investment analysis:** clearly separate user-entered prices from live prices, mark stale valuations, and avoid investment recommendations without risk profile, holdings quality, and current market data.

Each analysis should have a minimum sample/history requirement and return `insufficient_data` instead of a confident result.

**Exit criteria**

- Every insight has evidence, comparison window, calculation method, data sufficiency, and a linked action.
- A user can dismiss or mark an insight useful/inaccurate/too generic through the dashboard; broader snooze flows and model-training aggregation remain planned.
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
- [x] Add initial AI/insight feedback beyond thumbs up/down: stable IDs plus helpful, inaccurate, too-generic, dismissed, and additional safety/action labels through the audit contract. Feedback aggregation and snooze workflows remain planned.
- [x] Prefer deterministic responses for direct factual questions such as latest transaction, totals, largest categories, savings, and period comparisons. Use the LLM for explanation and planning.
- Add prompt/evaluation fixtures with adversarial questions, missing data, contradictory imports, prompt injection in merchant descriptions, and currency/date edge cases.

**Exit criteria**

- In an evaluation set, factual answers have zero unsupported numbers and high evidence-link coverage.
- AI can turn a recommendation into a confirmed UI action, and the action is auditable.
- When data is insufficient, the assistant explains exactly what would improve the answer.

### Phase 5 — Personalization, privacy, and resilience (ongoing)

**Outcome:** Ledger feels personal without becoming invasive or fragile.

- Add per-user preferences: categories, merchant aliases, pay cycle, recurring tolerance, risk comfort, household/shared expenses, and insight frequency.
- [x] Add portable export and confirmation-gated permanent account/data deletion.
- Add the remaining privacy controls: provider opt-in, cloud-data notice, retention period, delete conversations, and redact sensitive fields before AI calls.
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
