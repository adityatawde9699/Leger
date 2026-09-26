# API Reference

Base URL: `http://127.0.0.1:8000`  
Auth: `Authorization: Bearer <token>` on all endpoints.

## Health & Status
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/health` | — | `{"ok": true, "version": "1.4.0"}` |
| `GET` | `/currency/convert?amount=1000&base=INR&quote=USD` | amount and ISO currency codes | dated public reference-rate conversion; never changes stored ledger amounts |

## Transactions
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/transactions?cursor=&limit=&search=&category=&month=&type=&status=` | — | `PaginatedTransactions`; `status` may be `posted`, `pending`, or `excluded` |
| `POST` | `/transactions` | `TransactionIn` | `TransactionOut` |
| `POST` | `/transactions/split` | `SplitTransactionIn` (total and 2–10 category lines) | `SplitTransactionOut`; line amounts must add to total, and `client_request_id` supports retries |
| `PUT` | `/transactions/{id}` | `TransactionIn` | `TransactionOut` |
| `POST` | `/transactions/{id}/undo` | — | `TransactionOut`; restores the latest update when it has not already been undone |
| `DELETE` | `/transactions/{id}` | — | `{"deleted": true}` |

## Accounts
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/accounts` | — | `AccountOut[]`; credit accounts may include limit, minimum payment, and due date |
| `POST` | `/accounts` | `AccountIn` | `AccountOut` |
| `PUT` | `/accounts/{id}` | `AccountIn` | `AccountOut` |
| `DELETE` | `/accounts/{id}` | — | `{"deleted": true}` |

## Budgets
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/budgets` | — | `BudgetOut[]` |
| `PUT` | `/budgets` | `BudgetIn[]` | `BudgetOut[]`; upserts user budgets by category |

## Goals
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/goals` | — | `GoalOut[]` |
| `POST` | `/goals` | `GoalIn` | `GoalOut` |
| `PUT` | `/goals/{id}` | `GoalIn` | `GoalOut` |
| `DELETE` | `/goals/{id}` | — | `{"deleted": true}` |

## Personalization
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/categories` | — | built-in and active user categories |
| `POST` | `/categories` | `UserCategoryIn` | custom category |
| `DELETE` | `/categories/{id}` | — | deactivates a custom category without rewriting history |
| `GET` | `/merchant-aliases` | — | user-scoped alias list |
| `POST` | `/merchant-aliases` | `MerchantAliasIn` | creates/updates an alias and applies it to matching transactions |
| `DELETE` | `/merchant-aliases/{id}` | — | `{"deleted": true}` |
| `GET` | `/recurring` | — | confirmed recurring rules with evidence IDs |
| `POST` | `/recurring` | `RecurringRuleIn` | confirmed or pending user rule |
| `PUT` | `/recurring/{id}` | `RecurringRuleIn` | updated rule |
| `DELETE` | `/recurring/{id}` | — | `{"deleted": true}` |

`GET /profile` and `PUT /profile` also expose user-declared planning preferences: `pay_cycle` (`weekly`, `biweekly`, `monthly`, `irregular`), `risk_comfort` (`conservative`, `balanced`, `aggressive`, `not_sure`), `household_mode` (`individual`, `shared`), and `recurring_tolerance` (`strict`, `standard`, `flexible`). These are preferences, not inferred schedules, risk scores, or financial facts.

## Import
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `POST` | `/imports/sms` | `SmsParseRequest` | `TransactionOut[]` |
| `POST` | `/imports/sms/webhook` | `SmsWebhookRequest` | `TransactionOut[]` |
| `POST` | `/imports/statement` | `multipart/form-data` (`file`, optional `account_id`, optional JSON `excluded_row_fingerprints`, optional JSON `review_overrides`) | `ImportJobOut` (`202`); reviewed category/merchant/type overrides are keyed by preview row fingerprint and byte-identical re-uploads return the existing job |
| `GET` | `/imports/jobs?limit=` | 1–100 recent jobs | `ImportJobOut[]` |
| `POST` | `/imports/statement/preview` | `multipart/form-data` (`file`, optional `account_id`) | `ImportPreviewOut` with row fingerprints and category confidence |
| `GET` | `/imports/jobs/{id}` | — | `ImportJobOut` |
| `POST` | `/imports/jobs/{id}/retry` | — | `ImportJobOut` |
| `POST` | `/imports/jobs/{id}/cancel` | — | `ImportJobOut`; cancellation is cooperative and preserves already processed rows |

## AI Services
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `POST` | `/categorize` | `CategorizeSingleRequest` | `CategorizeSingleResponse` |
| `POST` | `/categorize/batch` | `CategorizeBatchRequest` | `TransactionOut[]` |
| `POST` | `/receipts/scan` | `multipart/form-data` | `ReceiptResult` |
| `POST` | `/transactions/{id}/receipt` | PNG/JPEG/WebP/PDF file (5 MB max) | Private user-owned attachment metadata; identical retry is idempotent |
| `GET` | `/transactions/{id}/receipt` | — | Private no-store attachment download |
| `DELETE` | `/transactions/{id}/receipt` | — | Remove attachment without deleting transaction |
| `GET` | `/insights/proactive` | — | `ProactiveInsight[]` with stable ID, quantified claim, evidence IDs, period/data-quality, method, confidence, recommended action, and lifecycle status |
| `GET` | `/bills/negotiate` | — | `NegotiationResult[]` |
| `POST` | `/advisor/stream` | `AdvisorRequest` (`question`, optional `conversation_id`, optional `answer_mode`: `quick`, `math`, or `plan`) | SSE stream; first event is `advisor.v1` metadata describing period, coverage, transaction count, profile currency, answer type, deterministic tool results, facts, assumptions, uncertainties, suggested actions, and source links |
| `GET` | `/ai/provider-health` | — | Credential-free configured/allowed state, circuit state, success/failure counters, and latest latency; never returns API keys or provider error text |
| `GET` | `/notifications?limit=20` | optional limit | user-owned in-app proactive notifications generated by the maintenance worker |
| `POST` | `/notifications/{id}/read` | — | marks one user-owned notification read |
| `POST` | `/advisor/actions/complete` | `AdvisorActionRequest` (`action_type`, optional evidence IDs/conversation ID) | Records explicit user confirmation of a suggested review/navigation action; does not mutate financial data |

## Analytics
| Method | Endpoint | Params | Response |
|---|---|---|---|
| `GET` | `/summary?month=&range=` | month (YYYY-MM) or `30d`, `3m`, `1y`, `all` | `SummaryOut` plus `data_quality`, shared evidence-bearing `analysis.claims`, canonical `analysis.insight_claims`/top-level `insight_claims`, and `analysis.fixed_flexible` committed/flexible spending classification |
| `GET` | `/daily-position?as_of=YYYY-MM-DD` | local calendar day within one day of server date | Current-month income, committed/flexible spending, confirmed upcoming obligations, and a guarded safe-to-spend estimate or explicit unavailable reasons |
| `POST` | `/daily-position/review` | `{confirmed: true}` | Audited timestamp confirming the user reviewed expected bills and budgets; expires for estimating after seven days or a plan change |
| `GET` | `/analytics/anomalies?range=` | `this_month`, `30d`, `3m`, `1y`, `all` | `{items, analysis}` with stable anomaly IDs, personal-baseline explanations, evidence transaction IDs, covered period, and sufficiency metadata; use `/insights/feedback` for review feedback |
| `GET` | `/analytics/forecast` | — | spending forecast plus budget warnings and covered-period/sufficiency metadata |
| `GET` | `/analytics/runway?as_of=&horizon_months=` | local date and 1–12 month horizon | deterministic reconciled-cash runway; irregular/mixed income returns low/typical/high assumptions and explicit data-quality warnings |
| `GET` | `/analytics/leakage` | — | evidence-backed price-increase, concentration, dormant-recurring, and possible-duplicate-service review candidates with method/period/action metadata; no automatic cancellation or claim of certainty |
| `GET` | `/analytics/compare?days=30&end=YYYY-MM-DD&comparison=mom|yoy` | equal-length comparison by default; `mom`/`yoy` selects calendar comparison | current vs previous period facts, category changes, evidence IDs, and insufficiency warnings |
| `POST` | `/analytics/scenario` | scenario type (`category_reduction`, `purchase`, `income_shock`, `savings_target`), category, reduction/income change percentages, one-time expense, target amount, horizon | deterministic what-if with baseline, projected cash flow, savings-target feasibility, and data quality |
| `POST` | `/insights/feedback` | `{insight_id, feedback, note?}` | auditable quality feedback without storing raw financial text |
| `GET` | `/insights/feedback/summary?days=90` | optional 1–365 day window | user-scoped text-free feedback counts grouped by label and stable insight family |
| `GET` | `/credit-health` | — | Personal cash-flow snapshot plus recorded credit-account readiness when user-entered limit, owed balance, minimum payment, and due date exist; no credit score or bureau assessment |
| `GET` | `/benchmarks` | — | Own posted-spending breakdown, currency and period, with `comparison_status: unavailable`; no synthetic percentiles or claimed peer sample |
| `GET` | `/gst/report?month=` | month (YYYY-MM) | `GSTReportOut` |

## Privacy and data control
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/export/full` | — | downloadable JSON containing portable user data (never secrets or statement payloads) |
| `DELETE` | `/profile/data` | `{"confirmation":"DELETE"}` | deletion counts; permanently removes the signed-in user's Ledger data |

`GET /profile` returns currency, region, income-pattern, onboarding-completion, `cloud_ai_enabled`, and `insight_frequency` preferences. `PUT /profile` accepts those fields; income pattern is user-declared context and does not itself change calculations. `insight_frequency=off` suppresses proactive insights and `important` retains only priority 4–5 observations; `daily` and `weekly` currently control filtering semantics only because scheduled push delivery is not implemented. When `cloud_ai_enabled` is false, deterministic advisor facts remain available, while open-ended explanations and proactive insights use deterministic fallbacks without calling a cloud provider. A currency change that would relabel existing monetary data returns `409`. New accounts must use the profile currency (`400` otherwise). `/summary` exposes `data_quality.currency_mismatch_count` for legacy accounts; `/advisor/stream` declines analysis while that count is nonzero.
Advisor and insight monetary text uses the profile currency without conversion; malformed proactive model output that uses a different currency is discarded. Legacy currency mismatches also suppress proactive insights until the account data is reconciled.
Provider selection is bounded by deployment configuration: timeout and maximum-attempt limits apply to router calls, and optional global/task provider allowlists prevent fallback to unapproved providers. Open-ended advisor requests may add one validated, read-only deterministic tool result to the `advisor.v1` metadata; tool arguments cannot select another user or mutate financial data.
Advisor conversations are automatically purged after the configured retention period; `DELETE /conversations/{id}` remains available for immediate user deletion.

## Investments
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/portfolios` | — | `PortfolioOut[]` |
| `POST` | `/portfolios` | `PortfolioIn` | `PortfolioOut` |
| `DELETE` | `/portfolios/{id}` | — | `{"deleted": true}` |
| `GET` | `/portfolios/{id}/holdings` | — | `HoldingOut[]` |
| `POST` | `/portfolios/{id}/holdings` | `HoldingIn` | `HoldingOut` |
| `PUT` | `/holdings/{id}` | `HoldingIn` | `HoldingOut` |
| `DELETE` | `/holdings/{id}` | — | `{"deleted": true}` |
| `GET` | `/portfolios/summary` | — | Portfolio summary JSON |
| `GET` | `/portfolios/analytics` | — | Portfolio metrics plus `valuation_quality`; prices are user-entered, live prices are unavailable, and stale holdings are identified |

## Platform
| Method | Endpoint | Params | Response |
|---|---|---|---|
| `GET` | `/export/{csv\|json\|tally}` | month | File download |
| `GET` | `/audit?resource_type=&limit=&offset=` | — | `AuditLogOut[]` |
| `GET` | `/webhooks` | — | `WebhookOut[]` |
| `POST` | `/webhooks` | `WebhookIn` | `WebhookOut` |
| `DELETE` | `/webhooks/{id}` | — | `{"deleted": true}` |

## Interactive Docs
Visit `http://127.0.0.1:8000/docs` for Swagger UI with try-it-out.
