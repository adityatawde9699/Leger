# Ledger improvement roadmap

## Product direction

Ledger should become a calm, trustworthy personal finance coach for ordinary people—not a dashboard full of charts or an AI chatbot that restates transactions.

The core promise should be:

> “Ledger helps me understand where my money is going, decide what to do next, and follow through—using evidence from my own data.”

The product should work for a first-time budgeter, a power user importing bank statements, and an Indian user managing UPI, cash, credit, investments, GST receipts, and irregular income. The app should feel useful with zero AI configuration and become more helpful—not merely more verbose—when AI is enabled.

This roadmap is based on the current implementation in `frontend/src`, `backend/app/main.py`, `backend/app/models.py`, and `backend/app/services`. It favors trust, data quality, and decision support before adding more surface area.

## Implementation status

Status reviewed: 2026-09-27. Completed items below are limited to behavior present in the current codebase and covered by the verification snapshot.

The first roadmap slice is now implemented: proactive insights expose evidence, confidence, source, action, and data-quality metadata; unsupported model insights are rejected; summary responses expose coverage warnings; the dashboard makes analytical limitations visible; statement imports can be previewed before commit, can be assigned to a user-owned account, use a database-backed payload with startup recovery and duplicate-claim protection, and support retrying failed jobs; the ledger distinguishes expenses, refunds, and transfers in core entry, filtering, balance, and summary flows; manual transactions enforce account ownership; account balances can be explicitly reconciled with an observed bank/wallet balance and audited; users can create and track savings, emergency-fund, debt, and custom goals with deadlines and progress; advisor streams now surface the period, coverage, and transaction count used for an answer; insight actions now navigate to the relevant activity view; and Analytics now includes an explainable scenario planner based on the user's recent history.
Privacy controls now include a full portable data export and an explicit, confirmation-gated permanent deletion flow exposed in Profile.
Profile now includes a per-user Cloud AI explanations preference with an explicit provider disclosure. Disabling it preserves deterministic factual answers and deterministic proactive-insight fallbacks and prevents those paths from calling the cloud router; provider retention policy is disclosed and unknown guarantees remain explicit.
AI provider routing now supports deployment-level and per-task allowlists, bounded provider timeout/attempt limits, policy-aware telemetry, fail-closed handling for malformed task policy, process-local circuit breakers, Redis-backed request budgets, deployment-wide health counters, and a credential-free provider health endpoint.
Backend development dependencies are now declared separately and GitHub Actions runs backend lint/tests plus the frontend production build on pushes and pull requests.
Phase 0 release safety is now documented in `docs/RELEASE-CHECKLIST.md`, and the frontend quality strategy is documented in `frontend/QUALITY.md`.
Privacy-safe structured telemetry now records operational latency, provider/fallback, parse success, evidence validation, feedback, correction, and import/insight outcomes without raw financial text.
Budgets now include active custom expense categories, preserve existing category budgets across taxonomy changes, accept history-based suggestions for custom categories, and show remaining daily allowance plus a clearly labeled month-end pace estimate.
The Dashboard now selects one data-aware next step from account setup, failed imports, pending or uncategorized transactions, stale/unassigned accounts, missing budgets, or missing goals; its transaction review actions open the matching Activity filter. The Docker entrypoint now passes migration Python through a quoted heredoc, has a runtime handoff regression test, and starts successfully in a built-image smoke test. A backend `.dockerignore` excludes local environments, databases, and secrets from image context.
First-run setup now saves region, record currency, and self-reported income pattern; users can optionally add a current-balance account snapshot and a goal before adding or importing activity. Profile changes that would relabel existing financial data are rejected, new accounts must match the ledger currency, and account forms use that currency without rounding away cents. Legacy account currency mismatches pause Dashboard, Budgets, Analytics, and Advisor analysis; the Accounts view avoids a mixed-currency total. Ledger still does not convert currencies.
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
Advisor facts, AI context, summary insight text, proactive insight text, and anomaly messages now use the profile currency instead of assuming rupees. A model-generated proactive insight that names another currency is rejected in favor of deterministic rules; currency changes invalidate the user's AI cache. India-specific benchmark and bill-negotiation logic still needs region-aware handling before those features are safe for every user.
Advisor SSE responses now use a versioned `advisor.v1` metadata contract. Deterministic answers expose facts, evidence, assumptions, uncertainties, suggested actions, and data-only source links; open-ended AI answers must return a validated JSON response with evidence-linked claims or are withheld. The Advisor UI labels calculation/explanation source, privacy state, uncertainty, and data range and can open the relevant workflow.
Proactive insight responses now carry a canonical `analysis` object with period, comparison period, method, cited transaction IDs, sufficiency, recommended action, and lifecycle status. Model and rule insight output is rejected when the claim is unquantified, lacks evidence, or lacks an actionable target.
Dashboard summary observations now expose the same evidence-bearing claim contract alongside the legacy display strings, and the Dashboard renders their method, confidence, evidence count, action, and usefulness feedback.
Anomaly and leakage candidates now expose the same period/method/sufficiency/action metadata, and Analytics links each candidate back to Activity with usefulness feedback for anomalies.
Open-ended advisor replies now pass a structured claim/evidence contract plus currency, amount, date, transaction-ID, and explicit merchant/category grounding checks before caching or persistence; invalid responses are replaced with a verification warning while deterministic factual answers remain preferred.
Advisor prompts now include a machine-readable deterministic facts block with totals, category totals, equal-length comparison values, evidence IDs, currency, period, and data-quality warnings; transaction descriptions are explicitly treated as untrusted content.
The former 300–900 behavioral “credit score” and synthetic “10,000+ urban users” percentile view have been removed because Ledger has no bureau data or verified peer dataset. The legacy routes now return recorded cash-flow/category facts plus, when users enter them, credit-account limit/owed/minimum-payment/due-date readiness facts; missing fields remain explicitly incomplete and the UI never presents invented ranks. Bill negotiation remains India-biased and needs a separate region-aware safety pass.

Verification snapshot: the last complete backend suite on the CI-targeted Python 3.12 environment passes (99 passed, 1 skipped, 4 FastAPI lifespan deprecation warnings), including persisted imports, entrypoint handoff, currency safeguards, USD AI-output checks, non-synthetic financial-picture endpoints, daily-position safety gates, split transactions, receipt privacy/deletion, evidence-backed committed/flexible spending analysis, personal historical budget pacing, irregular-income runway safeguards, leakage-candidate evidence, anomaly feedback/ID safety, explicit credit-account readiness, and stale investment valuation safety. The latest advisor, prompt-guard, proactive-insight, dashboard-claim, calendar-comparison, scenario, feedback, privacy, budget, backup, and notification focused suites pass 46 tests after adding structured source/action/uncertainty fields, answer modes, adversarial fixtures, monetary grounding checks, insight quality gates, calendar MoM/YoY coverage, savings-target feasibility checks, text-free feedback aggregation, request budgets, encrypted backup round trips, and notification policy coverage. Ruff, shell syntax (`backend/entrypoint.sh`), Python compilation, `git diff --check`, and the frontend production build pass; the Playwright Chromium smoke suite passes 3/3 latest core flows (also stable across a prior 9/9 repeat run): first-run setup/empty state, keyboard-reachable Quick Add, and command-palette focus restoration. The browser harness uses a same-origin API mock with service workers blocked to avoid false network failures. The local FastAPI TestClient currently hangs even with a minimal FastAPI app because the execution environment's AnyIO portal does not complete synchronous portal calls; this is not counted as a passing full-suite run. Rerun the full suite in CI or a normal host environment. The backend Docker image/startup smoke checks from the prior snapshot remain valid. The reported `/entrypoint.sh: 32: Syntax error: "(" unexpected` log has not been reproduced with this checkout; the running deployment image/script must be checked against the tested version.

Additional focused verification after the latest roadmap work passes 46 tests covering strict structured advisor responses, claim/evidence grounding, constrained model tool selection, bounded goal simulation, evidence-ID/date/entity validation, contradictory import review, auditable action safety, provider policy/timeout/circuit-breaker/health safety, shared-cache read-through/invalidation/fallback, database-visible cache versioning, sensitive-text redaction, conversation retention, preference/goal-only provider memory, insight-frequency filtering, editable import overrides, calendar comparisons, savings-target scenarios, text-free feedback aggregation, request budgets, encrypted backup round trips, notification policy, and cloud-AI-disabled fallbacks. Phase 5 is complete; external provider retention remains unknown unless the deployment supplies contractual policy values.

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
3. **AI output must remain contract-bound.** The advisor now uses deterministic fact tools plus a strict evidence-linked `advisor.v1` response contract; invalid structured output is withheld. Broader provider cost controls and evaluation depth remain separate operational work.
4. **Insight quality is limited by simplistic baselines.** Forecasting uses category-level EWMA with a minimum month threshold; anomaly detection uses global/category heuristics; recurring detection groups raw descriptions. These are useful starts, but they need data sufficiency checks, seasonality awareness, and user feedback.
5. **Import review still needs depth.** Statement processing now uses a database-backed payload, fresh worker sessions, startup recovery, retry, duplicate-claim protection, content/row fingerprints, durable progress, cooperative cancellation, pre-commit row exclusion, and user-edited inferred fields. Merchant alias management is available; broader import correction UX remains open. Ordinary transaction corrections have an auditable one-step undo.
6. **The AI contract is now visible but still operationally incomplete.** Deterministic answers, structured AI explanations, cloud-provider state, evidence range, and uncertainty are shown in the Advisor. Provider-specific retention guarantees and cost controls remain open.
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
- [x] Let users edit inferred import category, normalized merchant, and transaction type before commit; persist overrides by original row fingerprint so worker restarts and duplicate identity remain safe.
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

**Status: Complete (2026-09-26).**

- [x] Replace the feature-first first run with a short setup: region, record currency, income pattern, optional current-balance account snapshot, one account or import, and one goal. Each data-creation step can be skipped; setup state and preferences are stored on the user profile. Currency changes do not perform FX conversion and the app warns that mixed-currency totals are unsupported.
- [x] Enforce the single-currency setup for new accounts, preserve cents in displayed amounts, and pause Dashboard/Budgets/Analytics/Advisor views for legacy account currency mismatches. General mixed-currency analytics and conversion remain future work.
- [x] Give the dashboard a “Today / This month / Next action” hierarchy:
  - cash available and upcoming obligations;
  - income, committed spend, flexible spend, and remaining safe-to-spend amount;
  - one or two high-confidence observations;
  - a single recommended action with a completion button.
- [x] Add an empty-state path for no data, partial data, irregular income, and no budgets. Never show a “health score” without explaining that it is provisional. The Dashboard now withholds unsupported comparisons, explains missing history/data quality, and daily-position logic explicitly excludes unverified future income for irregular or mixed income patterns.
- [x] Add a lightweight goal model: emergency fund, debt payoff, spending reduction, savings target, or custom goal. Track target, deadline, and current progress; contribution guidance remains open.
- [x] Redesign budgets around decisions: history-based suggested baseline (including custom categories), user target, remaining amount, month-end pace estimate, and a remaining daily allowance—not only a red/green percentage.
- [x] Add “safe to spend” only after committed bills, budgeted obligations, upcoming recurring payments, and data freshness are known. Label it as an estimate, never as a bank balance.
- [x] Improve mobile quick capture: amount-first entry, merchant/category suggestions, receipt attachment, split transaction, recurring toggle, and offline queue with sync status.
- [x] Consolidate primary navigation around Home, Budgets, Goals, and Ask Ledger, with Activity and advanced areas under the secondary “More” navigation.
- [x] Add accessibility work: keyboard support, focus management for sheets/dialogues, screen-reader labels, color-independent status, reduced motion, and readable contrast.

**Exit criteria**

- [x] A new user can add/import data and receive one useful, explainable next action without visiting multiple advanced screens.
- [x] Every important empty state explains what is missing and how to fix it.
- [x] The dashboard answers “Where am I?”, “What changed?”, and “What should I do next?” in under a minute.

### Phase 3 — Build evidence-based analysis (4–6 weeks)

**Outcome:** Analysis is genuinely insightful, not a list of generic observations.

**Status: complete.** The shared analysis contract, comparison modes, deterministic scenarios, evidence-linked insight quality gates, and seven-day snooze feedback flow are implemented and verified.

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

- [x] **Period comparisons:** equal-length configurable windows plus calendar month-over-month and year-over-year comparisons with current/prior totals, category deltas, evidence IDs, and `insufficient_data`.
- [x] **Fixed vs flexible spending:** identify recurring/committed obligations separately from discretionary categories using confirmed rule evidence; unmatched transactions remain flexible.
- [x] **Cash-flow runway:** forecast near-term balance using fresh reconciled cash accounts, confirmed recurring payments, posted spending, and observed income; show an explicit low/typical/high range when income is irregular.
- [x] **Budget pacing:** compare actual daily pace with remaining days and the user's prior monthly pace, not only month-end extrapolation.
- [x] **Merchant and subscription leakage:** detect price increases, duplicate services, dormant recurring payments, and concentration risk as review candidates, each with supporting transaction/rule evidence.
- [x] **Anomalies with explanations:** use personal/category baselines, amount/date and duplicate similarity; stable anomaly IDs now expose the explanation and accept helpful/inaccurate false-positive feedback.
- [x] **Insight quality gate:** normalize proactive insight evidence/action metadata and reject unquantified or unsupported model/rule filler before it reaches the UI.
- [x] **Goal scenarios:** deterministic category reduction, purchase affordability, income shock, and savings-target projections are available through Analytics with required monthly saving and feasibility outputs.
- [x] **Debt and credit readiness:** record explicit credit-account limit, amount owed, minimum payment, and due date; expose only deterministic readiness facts when those fields exist, and never label a proxy score as a bureau score.
- [x] **Investment analysis safety slice:** clearly separate user-entered prices from live prices, mark stale valuations, and avoid investment recommendations without risk profile, holdings quality, and current market data. Live market feeds and personalized recommendations remain out of scope.

Each analysis should have a minimum sample/history requirement and return `insufficient_data` instead of a confident result.

**Exit criteria**

- [x] Every insight has evidence, comparison window, calculation method, data sufficiency, and a linked action.
- [x] A user can snooze an insight for seven days or mark it useful/inaccurate/too generic through the dashboard; feedback is recorded with stable insight IDs and available as text-free, user-scoped quality aggregates grouped by feedback label and insight family.
- [x] Generic outputs such as “review your spending” are rejected unless they include a quantified reason and an actionable target.

### Phase 4 — Make AI a grounded copilot (4–6 weeks)

**Outcome:** AI helps the user reason and act, while calculations and permissions remain deterministic.

**Status: complete.** Open-ended answers are contract-bound, evidence-linked, privacy-labeled, and withheld when grounding fails; deterministic facts and confirmed UI actions remain authoritative.

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

- [x] Add the deterministic fact-tool registry: `get_summary`, `compare_periods`, `list_evidence`, `get_recurring`, and `open_transactions`/budget evidence results are calculated in Python and included in advisor context and metadata.
- [x] Add the initial model-selected, read-only tool call: the model may request one allowlisted fact tool, Python validates bounded arguments and current-user evidence, and the result is returned to the advisor context.
- [x] Add bounded read-only `simulate_goal` support using the existing deterministic scenario engine; assumptions, history evidence, data quality, and horizon/input limits are returned with the result. Analytics additionally supports purchase, income-shock, category-reduction, and savings-target scenarios.
- [x] Return a structured advisor response: `answer`, `facts`, `assumptions`, `uncertainties`, `suggested_actions`, and `source_links`. Open-ended model output now has a strict JSON `advisor.v1` contract and is withheld when the contract is invalid.
- [x] Ground every generated claim against current Ledger evidence. Every structured factual claim requires current-user transaction IDs; answer/claim amounts, dates, transaction IDs, currencies, and explicitly labeled entities are validated before display, persistence, or caching.
- [x] Add an answer mode selector: “quick answer,” “show the math,” and “plan with me.” The selector changes explanation style only and does not authorize financial mutations.
- [x] Add conversation memory only for explicit user preferences/goals, not unrestricted financial history, and recompute facts at request time.
- [x] Show “calculated by Ledger” versus “explained by AI,” provider/privacy status, and the data range used through explicit `advisor.v1` provenance metadata.
- [x] Add the structured `advisor.v1` response contract with facts, assumptions, uncertainties, suggested actions, data-only source links, explicit calculation/explanation/privacy provenance, and claim-level evidence IDs.
- [x] Add the open-ended grounding guard for amounts, currencies, dates, transaction IDs, and explicitly labeled merchant/category entities; invalid JSON or unsupported claims are replaced with a safe verification response before caching or persistence.
- [x] Extend the advisor output guard to reject explicit dates, UUID transaction identifiers, and explicitly labeled merchant/category claims that are absent from the current context; the model is required to put factual claims in the evidence-linked claim list.
- [x] Add a deterministic no-history advisor gate that explains the missing data and next setup action without calling cloud AI.
- [x] Add an auditable advisor action confirmation endpoint and UI completion control for suggested review/navigation actions; model actions remain non-mutating and require user confirmation.
- [x] Add adversarial prompt/evaluation fixtures covering prompt injection, merchant-like hostile text, message separation, currency handling, input-length limits, date boundaries, contradictory import inference versus user review, structured-response violations, and unsupported claims.
- [x] Add initial AI/insight feedback beyond thumbs up/down: stable IDs plus helpful, inaccurate, too-generic, dismissed, snoozed, and additional safety/action labels through the audit contract, with text-free quality aggregation at `/insights/feedback/summary`.
- [x] Prefer deterministic responses for direct factual questions such as latest transaction, totals, largest categories, savings, and period comparisons. Use the LLM for explanation and planning.
- [x] Add prompt/evaluation fixtures with adversarial questions, missing data, contradictory imports, prompt injection in merchant descriptions, structured-response violations, and currency/date/entity edge cases.

**Exit criteria**

- [x] In the focused evaluation set, factual structured answers have zero accepted unsupported numbers/dates/IDs/entities and 100% evidence-link coverage for accepted factual claims; invalid model output is withheld.
- [x] AI can turn a recommendation into a confirmed UI review/navigation action, and the confirmation is auditable; financial mutations still require their existing dedicated confirmation flows.
- [x] When data is insufficient, the assistant explains what is missing and the concrete setup/import action that would improve the answer.

### Phase 5 — Personalization, privacy, and resilience

**Outcome:** Ledger feels personal without becoming invasive or fragile.

**Status: complete.** Phase 5 controls, maintenance jobs, notification policy, encrypted backup/restore primitives, and operational AI safeguards are implemented and verified. External provider retention remains disclosed as unknown unless the deployment supplies contractual policy values.

- [x] Add persisted per-user preferences for custom categories/merchant aliases, pay cycle, risk comfort, household scope, insight frequency, and recurring-detection tolerance, with clear disclosure that these are user-declared preferences rather than inferred facts or regulated scores. Strict/standard/flexible tolerance now changes recurring suggestion sensitivity; confirmed rules still require explicit action.
- [x] Add portable export and confirmation-gated permanent account/data deletion.
- [x] Add the initial per-user cloud AI control and Profile disclosure. Disabled users retain deterministic factual answers and deterministic proactive-insight fallbacks; provider retention policy is disclosed explicitly.
- [x] Add deployment-configured conversation retention (90-day default), immediate conversation deletion, and broad sensitive-field redaction before advisor provider calls.
- [x] Limit provider-bound conversation memory to explicit user preferences/goals and recompute current financial facts per request; unrestricted financial-history replay remains excluded.
- [x] Add persisted proactive insight frequency controls (`off`, `important`, `daily`, `weekly`) and honor them through the maintenance worker, quiet-hours policy, daily cap, and in-app notifications.
- [x] Add deployment-configured provider retention disclosure and broader sensitive-field redaction before every AI call; unknown provider guarantees remain explicitly unknown until contractual provider commitments are supplied.
- [x] Add the provider-routing safety slice: per-task/global provider allowlists, bounded timeout and attempt limits, policy-aware telemetry, fail-closed handling for malformed task policy, cooldown circuit breakers, request budgets, and deployment-wide Redis health counters.
- [x] Add database-visible per-user cache-version keys for advisor, anomaly, forecast, and proactive insight results so multi-worker reads do not rely only on process-local invalidation or wall-clock TTL.
- [x] Make AI provider routing fully observable and resilient: circuit breakers, latency counters, credential-free provider health, Redis-backed daily request budgets, deployment-wide health counters, and shared cache policy are implemented.
- [x] Move derived-value TTL caches to an optional Redis shared cache for multi-worker deployments, with local fallback and user-scoped invalidation; cache keys also include database-visible data versions.
- [x] Add background jobs for recurring detection, deterministic insight generation, statement processing, conversation retention, and in-app notification delivery. The maintenance worker is bounded, recoverable, and never calls cloud AI.
- [x] Add notification preferences with quiet hours and a strict daily cap on proactive messages; notifications are user-owned, listable, and markable as read.
- [x] Support authenticated encrypted backups and explicit-confirmation restore testing for the portable export. Configure `BACKUP_ENCRYPTION_KEY` before enabling the endpoints.

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
