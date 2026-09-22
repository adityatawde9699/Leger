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
| `account_id` | Optional user-owned account. Missing account assignment reduces balance confidence for non-cash entries. |
| `source=cash` | Manual cash/wallet movement; included in cash totals and does not require an account. |
| `source=bank` | Manual entry associated with a selected account. |
| `source=statement` | Parsed bank/card statement row; `source_ref` is an idempotency fingerprint. |
| `source=sms` | Parsed SMS notification; `source_ref` is a stable message fingerprint. |
| `source=receipt` | Receipt OCR result. |

`source_ref` is an import identity, not proof that a transaction is economically unique. Users can still record legitimate same-day same-value transactions when their account/type/description identity differs.

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
- Period comparisons use two adjacent windows of the same length (7–365 days). A comparison is `insufficient_data` when either window has no transactions; percentage change is omitted when the prior value is zero. Each change retains the transaction IDs from both windows.

## Import identity

- A file fingerprint is SHA-256 of the uploaded bytes and prevents byte-identical re-upload jobs for the same user/account.
- A statement-row fingerprint includes the account identity, transaction type, date, amount, and normalized description.
- A duplicate suspect is a review signal, not an automatic deletion decision.
- Statement preview fingerprints can be submitted as `excluded_row_fingerprints` so uncertain rows are retained in the source file but not committed as transactions.

Analysis responses also expose `income_confidence` (`none`, `low`, `medium`, or `high`) and, on user summaries, `account_balance_quality` (`none`, `reconciled`, or `mixed_or_unreconciled`). These describe evidence quality, not a guarantee that external accounts are current.

## Currency and limits

- Amounts currently use the account/summary currency display contract, defaulting to INR.
- Currency conversion is not performed implicitly; mixed-currency accounts require explicit product support before being combined.
- Dates in the future are rejected by statement parsing.
