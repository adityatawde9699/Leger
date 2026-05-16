# API Reference

Base URL: `http://127.0.0.1:8000`  
Auth: `Authorization: Bearer <token>` on all endpoints.

## Transactions
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `GET` | `/transactions?page=1&size=20&q=&category=&month=` | — | `PaginatedTransactions` |
| `POST` | `/transactions` | `TransactionIn` | `TransactionOut` |
| `PUT` | `/transactions/{id}` | `TransactionIn` | `TransactionOut` |
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

## Import
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `POST` | `/sms/parse` | `SmsParseRequest` | `TransactionOut[]` |
| `POST` | `/import/csv` | `multipart/form-data` | `ImportJobOut` |
| `POST` | `/import/pdf` | `multipart/form-data` | `ImportJobOut` |

## AI Services
| Method | Endpoint | Body | Response |
|---|---|---|---|
| `POST` | `/categorize` | `CategorizeSingleRequest` | `CategorizeSingleResponse` |
| `POST` | `/categorize/batch` | `CategorizeBatchRequest` | `TransactionOut[]` |
| `POST` | `/receipt/scan` | `multipart/form-data` | `ReceiptResult` |
| `GET` | `/insights/proactive` | — | `ProactiveInsight[]` |
| `GET` | `/bills/negotiate` | — | `NegotiationResult[]` |
| `POST` | `/advisor` | `AdvisorRequest` | SSE stream |

## Analytics
| Method | Endpoint | Params | Response |
|---|---|---|---|
| `GET` | `/summary?month=` | month (YYYY-MM) | `SummaryOut` |
| `GET` | `/credit-health` | — | `CreditHealthOut` |
| `GET` | `/benchmarks` | — | `BenchmarkOut` |
| `GET` | `/gst/report?month=` | month (YYYY-MM) | `GSTReportOut` |

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
