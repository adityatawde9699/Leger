# Ledger data dictionary

This is the calculation contract used by the API and analytics services. New financial features should preserve these meanings or update this document and the relevant tests together.

## Transactions

| Field | Meaning |
|---|---|
| `date` | Calendar date supplied by the user or statement. Ledger does not infer an intraday timezone from a date-only value. |
| `type=income` | Money received; contributes positively to income and net cash flow. |
| `type=expense` | Money spent; contributes positively to expense totals and negatively to net cash flow. |
| `type=refund` | Money returned from a prior expense; offsets expense totals and contributes positively to net cash flow. |
| `type=reimbursement` | Money repaid by another person/employer for an expense; behaves like a refund in cash-flow math but remains distinguishable for review. |
| `type=transfer` | Movement between accounts; excluded from income and expense totals. |
| `status=posted` | Confirmed movement included in balances and analysis. |
| `status=pending` | Visible movement awaiting confirmation; excluded from committed balances and AI analysis. |
| `status=excluded` | Retained for audit/review but intentionally excluded from balances and analysis. |
| `amount` | Always a positive decimal magnitude. Sign is derived from `type`, never stored as a negative amount. |
| `source_ref=split:<id>` | Several atomic expense rows are parts of one purchase. Their amounts sum to the original total; no duplicate parent expense is stored. |
| `source_ref=offline:<id>` | A user-initiated quick-capture request ID. Retrying that request reuses the same transaction instead of creating a normal duplicate. |
| `account_id` | Optional user-owned account. Missing account assignment reduces balance confidence for non-cash entries. |
| `source=cash` | Manual cash/wallet movement; included in cash totals and does not require an account. |
| `source=bank` | Manual entry associated with a selected account. |
| `source=statement` | Parsed bank/card statement row; `source_ref` is an idempotency fingerprint. |
| `source=sms` | Parsed SMS notification; `source_ref` is a stable message fingerprint. |
| `source=receipt` | Receipt OCR result. |

`source_ref` is a source or client-request identity, not proof that a transaction is economically unique. A split group deliberately shares one identity across its component rows. Users can still record legitimate same-day same-value transactions when their account/type/description identity differs.

Receipts are private attachments to one user-owned transaction. They are not used in financial calculations or sent to AI by default; full export includes their bytes as base64, and deleting a transaction removes its attachment.

## Daily position

`safe_to_spend_estimate` is not a bank balance. It is the sum of fresh, explicitly reconciled active cash-account snapshots minus the larger of each category's remaining monthly budget or confirmed upcoming bills in that category. Future income is excluded. Ledger withholds the estimate if imports or transactions are pending, account linkage/currency/balance freshness is unreliable, a credit account has unverified payment obligations, budgets are missing, a bill date is stale, or the user's explicit obligations review has expired or predates a plan change. The review is auditable and does not certify that Ledger discovered every bill.

## Accounts and balances

- `Account.balance` is the latest user-observed or calculated balance for that account, not a guaranteed live bank balance.
- `last_reconciled_balance` and `last_reconciled_at` record the last explicit real-world check.
- A transaction `running_balance` is the bank-reported balance after that row when supplied by a statement.
- The dashboard should disclose missing account assignments, stale/manual balances, and incomplete history before presenting balance-sensitive guidance.

## Analysis conventions

- All financial arithmetic uses decimal values in the backend and rounds for presentation only.
- Refunds offset expenses; transfers are excluded from income, expenses, savings rate, forecasts, budgets, and scenarios.
- Analysis responses should include period start/end, transaction count, coverage, and warnings.
- `confidence` describes the reliability of an inference, not the user's financial health.
- “Calculated by Ledger” means deterministic code produced the number. “Explained by AI” means a configured provider generated language around Ledger context.
- `User.cloud_ai_enabled` is the per-user control for cloud explanations. `false` preserves deterministic facts and rule-based insight fallbacks and prevents the proactive-insight and open-ended advisor paths from calling a configured cloud provider; it does not delete existing data.
- `User.insight_frequency` is `off`, `important`, `daily`, or `weekly`. `off` returns no proactive insights; `important` returns only priority 4–5 items. `daily` and `weekly` are stored user intent until a notification scheduler exists.
- Advisor provider context redacts common contact and long account identifiers before transmission. Conversation retention is deployment-configured (`AI_CONVERSATION_RETENTION_DAYS`, default 90); deletion removes the conversation and its messages.
- Provider retention is disclosed from the deployment's `AI_PROVIDER_RETENTION_POLICY` map; an absent provider entry is shown as unknown, never treated as a guarantee. Broader redaction also covers IBANs, bank-account-like identifiers, URLs, payment-card-like identifiers, PANs, emails, and phones.
- `User.quiet_hours_start`, `User.quiet_hours_end`, and `User.proactive_daily_cap` govern deterministic in-app proactive notification delivery. The maintenance worker generates at most one notification per user per day and does not call cloud AI.
- `/advisor/stream` begins with an `advisor.v1` metadata event. Deterministic answers populate `facts`, `evidence`, `assumptions`, `uncertainties`, `suggested_actions`, and `source_links`; links are data-only descriptors and never model-executed URLs. AI answers retain the same fields and must disclose uncertainty when they do not carry structured evidence.
- Proactive insights expose an `analysis` object containing the covered period, optional comparison period, calculation method, cited transaction IDs, and a sufficiency flag. A surfaced insight must contain a measurable claim, evidence, and a recommended action; otherwise model output is discarded.
- Open-ended advisor output is checked before persistence for explicit currency-coded monetary claims. A claim is accepted only when its amount appears in the current context and its currency matches the profile currency; otherwise the user receives a verification warning.
- Advisor output also rejects explicit dates and UUID transaction identifiers that are not present in the current context; unsupported claims are replaced with a verification warning before caching or persistence.
- Advisor context includes a machine-readable deterministic facts block containing totals, category totals, comparison periods/values, evidence IDs, currency, and data quality. This is the source of truth for AI explanation; raw transaction descriptions are untrusted content.
- Period comparisons use two adjacent windows of the same length (7–365 days). A comparison is `insufficient_data` when either window has no transactions; percentage change is omitted when the prior value is zero. Each change retains the transaction IDs from both windows.
- `analysis.fixed_flexible` classifies posted spending as committed only when it matches a confirmed active recurring rule by evidence ID or by normalized merchant, category, and amount range. Unmatched spending remains flexible; the entire category is never treated as fixed merely because one recurring rule exists.
- Forecast budget warnings include the current month-end projection and, when available, the average of up to the prior three observed monthly totals for the same category. `pace_delta` is the difference between those values; it is a personal reference, not a peer benchmark.
- `/analytics/runway` uses only fresh reconciled cash-account snapshots. It subtracts observed flexible spending and confirmed recurring obligations, and reports future income as an assumption. For irregular or mixed income, the low bound is zero until enough monthly history exists; missing reconciliation or history produces warnings instead of a confident runway.
- Leakage candidates are review signals. Price increases require four observations; concentration requires at least two transactions and a 30% share; dormant payments use confirmed rules and overdue dates; duplicate services require overlapping category/amount evidence. None triggers an automatic cancellation or deletion.
- Anomalies are personal-baseline review leads, not fraud determinations. Each stable `anomaly:<type>:<transaction_id>` ID carries a human-readable comparison/range and can receive `helpful` or `inaccurate` feedback through the existing audit contract.
- Credit readiness is limited to user-entered account facts: positive amount owed, credit limit, minimum payment, and next due date. Utilization is `owed / limit`; missing fields produce an incomplete state. Ledger never derives a credit score or repayment-history claim from cash-flow behavior.
- Investment `current_price` is user-entered, not a live market quote. Portfolio analytics reports the price source and marks holdings stale when no update timestamp exists, the price is zero, or the entered value is older than 30 days. Ledger does not make investment recommendations without market/risk data.

## Import identity

- A file fingerprint is SHA-256 of the uploaded bytes and prevents byte-identical re-upload jobs for the same user/account.
- A statement-row fingerprint includes the account identity, transaction type, date, amount, and normalized description.
- A duplicate suspect is a review signal, not an automatic deletion decision.
- Statement preview fingerprints can be submitted as `excluded_row_fingerprints` so uncertain rows are retained in the source file but not committed as transactions.
- Statement preview fingerprints can also carry user-confirmed `review_overrides` for category, normalized merchant, and transaction type. Overrides win over AI inference and are applied before commit while the original description remains unchanged.

Analysis responses also expose `income_confidence` (`none`, `low`, `medium`, or `high`) and, on user summaries, `account_balance_quality` (`none`, `reconciled`, or `mixed_or_unreconciled`). These describe evidence quality, not a guarantee that external accounts are current.

## Currency and limits

- The user profile selects the currency used for new financial records (default INR) and the locale. Changing it is rejected when existing amounts use another currency; a legacy account already in the target currency can be aligned with the profile if no unassigned monetary records exist. New accounts must match the profile currency. Older accounts in multiple currencies have no combined total in the Accounts view; Dashboard, Budgets, Analytics, and Advisor pause their user-facing analysis when account currencies differ from the profile setting.
- Income pattern is a user-declared preference (`regular`, `irregular`, `mixed`, or `not_sure`). It is not a verified income schedule and does not yet change projections.
- Pay cycle is a user-declared planning preference (`weekly`, `biweekly`, `monthly`, or `irregular`); it is not inferred from transactions. Risk comfort (`conservative`, `balanced`, `aggressive`, or `not_sure`) is a stated preference only, never a regulated risk score. Household mode (`individual` or `shared`) describes the scope the user intends to track. Recurring tolerance (`strict`, `standard`, or `flexible`) changes the sensitivity of recurring-payment suggestions; confirmed rules still require explicit user action.
- Currency conversion is not performed implicitly; mixed-currency accounts require explicit product support before being combined.
- The Currency Converter is an explicit display utility using dated Frankfurter reference rates. It does not convert stored transactions, account balances, budgets, or goals, and its result should not be treated as a settlement or live trading quote.
- Dates in the future are rejected by statement parsing.
