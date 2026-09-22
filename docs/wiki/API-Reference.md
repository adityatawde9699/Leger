# API Reference

Base URL: `http://127.0.0.1:8000`  
Auth: `Authorization: Bearer <token>` on all endpoints.

## Health & Status
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/health` | — | `{"ok": true, "version": "1.0.1"}` |

## Transactions
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/transactions?cursor=&limit=&search=&category=&month=&type=&status=` | — | `PaginatedTransactions`; `status` may be `posted`, `pending`, or `excluded` |
| `POST` | `/transactions` | `TransactionIn` | `TransactionOut` |
| `PUT` | `/transactions/{id}` | `TransactionIn` | `TransactionOut` |
| `POST` | `/transactions/{id}/undo` | — | `TransactionOut`; restores the latest update when it has not already been undone |
| `DELETE` | `/transactions/{id}` | — | `{"deleted": true}` |

## Accounts
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/accounts` | — | `AccountOut[]` |
| `POST` | `/accounts` | `AccountIn` | `AccountOut` |
| `PUT` | `/accounts/{id}` | `AccountIn` | `AccountOut` |
| `DELETE` | `/accounts/{id}` | — | `{"deleted": true}` |

## Budgets
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/budgets` | — | `BudgetOut[]` |
| `POST` | `/budgets` | `BudgetIn` | `BudgetOut` |
| `PUT` | `/budgets/{id}` | `BudgetIn` | `BudgetOut` |
| `DELETE` | `/budgets/{id}` | — | `{"deleted": true}` |

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

## Import
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `POST` | `/imports/sms` | `SmsParseRequest` | `TransactionOut[]` |
| `POST` | `/imports/sms/webhook` | `SmsWebhookRequest` | `TransactionOut[]` |
| `POST` | `/imports/statement` | `multipart/form-data` (`file`, optional `account_id`, optional JSON `excluded_row_fingerprints`) | `ImportJobOut` (`202`); byte-identical re-uploads return the existing job |
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
| `GET` | `/insights/proactive` | — | `ProactiveInsight[]` |
| `GET` | `/bills/negotiate` | — | `NegotiationResult[]` |
| `POST` | `/advisor/stream` | `AdvisorRequest` | SSE stream; first event is metadata describing period, coverage, transaction count, answer type, and (for deterministic answers) evidence/assumptions |

## Analytics
| Method | Endpoint | Params | Response |
|---|---|---|---|
| `GET` | `/summary?month=&range=` | month (YYYY-MM) or `30d`, `3m`, `1y`, `all` | `SummaryOut` plus `data_quality` and shared evidence-bearing `analysis.claims` |
| `GET` | `/analytics/anomalies?range=` | `this_month`, `30d`, `3m`, `1y`, `all` | `{items, analysis}` with anomaly evidence, covered period, and sufficiency metadata |
| `GET` | `/analytics/forecast` | — | spending forecast plus budget warnings and covered-period/sufficiency metadata |
| `GET` | `/analytics/compare?days=30&end=YYYY-MM-DD` | equal-length comparison window | current vs previous period facts, category changes, evidence IDs, and insufficiency warnings |
| `POST` | `/analytics/scenario` | category, reduction/income change percentages, one-time expense, horizon | deterministic what-if with baseline, projected cash flow, and data quality |
| `POST` | `/insights/feedback` | `{insight_id, feedback, note?}` | auditable quality feedback without storing raw financial text |
| `GET` | `/credit-health` | — | `CreditHealthOut` |
| `GET` | `/benchmarks` | — | `BenchmarkOut` |
| `GET` | `/gst/report?month=` | month (YYYY-MM) | `GSTReportOut` |

## Privacy and data control
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/export/full` | — | downloadable JSON containing portable user data (never secrets or statement payloads) |
| `DELETE` | `/profile/data` | `{"confirmation":"DELETE"}` | deletion counts; permanently removes the signed-in user's Ledger data |

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
