# Security operations

## Data and retention

Transactions, accounts, budgets, receipts, audit records, notifications, and webhook metadata
remain until the user deletes them or deletes account data. Statement import payloads are
temporary job data; successful jobs clear the stored bytes. AI conversations are purged after
`AI_CONVERSATION_RETENTION_DAYS` (default 90) by maintenance. Caches expire according to their
individual TTLs and should not be treated as records. Portable exports contain financial data
and receipt bytes. Encrypted backups remain wherever the user or operator stores them; deleting
an account does not delete external backup copies. Provider telemetry contains operational
metadata; check each configured provider's retention policy before enabling cloud AI. New
accounts start with cloud AI disabled.

## Incident response

The on-call owner records the incident time, affected environment, request IDs, and relevant
audit records. Preserve a read-only evidence copy before cleanup. Never include bearer tokens,
cookies, webhook signing keys, receipt content, or full financial payloads in tickets or logs.

| Event | Immediate containment | Recovery |
| --- | --- | --- |
| Session compromise | Revoke affected rows in `app_sessions`; restrict affected accounts | Have users sign in again; review exports and deletes |
| Webhook key compromise | Disable affected webhook; rotate signing key | Test new delivery, notify integration owner, retire old key |
| Database exposure | Isolate database and revoke access credentials | Rotate webhook and backup keys, assess exposed records, restore clean service |
| Provider data incident | Disable cloud AI and affected provider key | Review provider retention, assess disclosures, rotate key |
| Malicious import | Cancel affected import jobs and isolate uploaded files | Review transactions and audit trail; restore affected records |
| Accidental deletion | Stop writes to affected records | Restore from encrypted backup; verify ownership and reconciliation |

The owner assesses legal and contractual notification requirements with counsel, informs
affected users when required, and records the final timeline and corrective actions. Run a
tabletop drill for session compromise and a backup restore before calling this runbook tested.

## Webhook verification

The receiver should compute HMAC-SHA256 over the exact raw request body using its current
signing secret and compare it in constant time with `X-Ledger-Signature` after the `sha256=`
prefix. Parse `X-Ledger-Timestamp` as UTC, require it to match the signed body timestamp, and
reject timestamps more than five minutes old or in the future. Keep a short-lived replay cache
of signature values and reject duplicates. The rotation endpoint sends a `webhook.test` event
with the proposed new key and activates it only after a successful response.

## Monitoring

Alert on repeated 401/403 responses, high rate-limit counts, export and delete bursts, repeated
webhook failures, AI provider failures and budget exhaustion, database connection failures, and
failed schema migrations. Production startup must reject a non-Google auth provider, missing
shared Redis, or missing encryption keys. Review alerts with request IDs and user IDs only.
