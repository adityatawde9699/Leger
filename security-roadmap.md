# Ledger Security Roadmap

Last audited: 2026-09-29  
Implementation update: 2026-09-29. Application changes below are implemented locally; production configuration, CI scans, external review, and incident drill still require deployment or external execution.
The findings section records the audit baseline. The phase checkboxes record the current implementation state.
Scope: backend API, frontend authentication, AI integrations, uploads, webhooks, deployment configuration, and user-owned financial data.

## Security position today

Ledger has a good security baseline for an early personal-finance product, but it is not yet at a mature financial-data security standard.

Current posture: **medium risk**.

The strongest controls are Google token verification in production, user-scoped database access in most endpoints, SSRF protection for webhooks, HMAC webhook delivery, bounded receipt attachments, encrypted backups when configured, AI redaction, rate limits on expensive routes, and a non-root Docker runtime.

The implementation now addresses browser token storage, webhook encryption, bounded upload reads, API headers, shared rate limiting, and DNS rebinding in webhook delivery. The remaining risks are incomplete endpoint-by-endpoint authorization coverage, unverified production configuration, security scans that have not yet run in CI, and operational work requiring external execution.

## Confirmed controls

- Production authentication is Google-only; `AUTH_PROVIDER=dev` is rejected in production.
- Google ID tokens are checked server-side against the configured client ID and verified email status.
- API requests use bearer authentication and user IDs are taken from the verified identity, not request payloads.
- Most resource queries include an ownership condition such as `resource.user_id == user.id`.
- Webhook registration and delivery validate public HTTP(S) destinations to reduce SSRF risk.
- Webhook requests are HMAC-SHA256 signed.
- Receipt attachments use content signatures, a 5 MB bounded read, private cache headers, and ownership checks.
- Statement imports enforce file extensions, upload bounds, row limits, and background-job recovery.
- AI context has deterministic redaction for email, phone, PAN, IBAN, card-like, URL, and account-like identifiers.
- AI conversations have configurable retention and user deletion support.
- Backup exports can be encrypted with Fernet.
- The production container runs as a non-root user.
- Frontend deployment headers include `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy`.

## Priority findings

### P0 — must fix before treating the app as high-trust financial software

#### P0.1 Browser bearer token in localStorage

Google ID tokens are stored in `localStorage` in `frontend/src/googleAuth.js`. Any future XSS, compromised dependency, or unsafe third-party script could read the token and impersonate the user until expiry.

Target: replace browser-readable token storage with a backend-managed session using a `Secure`, `HttpOnly`, `SameSite` cookie, short session lifetime, rotation, and explicit logout/revocation behavior.

#### P0.2 Encrypted webhook secrets

Webhook secrets are currently stored as plaintext in the `webhooks.secret` database column. A database backup or read-only database compromise would expose signing keys.

Target: encrypt secrets with a deployment-managed encryption key, never return them after creation, redact them from exports/logs, and provide rotation.

#### P0.3 Complete ownership/IDOR test coverage

The application generally scopes queries to the authenticated user, but financial applications need endpoint-by-endpoint proof. Add tests for every read, update, delete, download, retry, restore, and export route using two users.

Target: an automated cross-user authorization suite with zero unauthorized data access and no endpoint relying only on an opaque ID lookup.

### P1 — high priority hardening

#### P1.1 Strict request/upload limits

Every `UploadFile` path must read at most its configured maximum plus one byte. Receipt scanning currently needs the same bounded-read behavior as receipt attachment. Apply limits to avatar data, JSON body size, CSV/PDF parsing, image dimensions, and decompression expansion.

Target: no request can allocate unbounded memory from client-controlled input.

#### P1.2 Security headers at the API boundary

Add API middleware for:

- `Strict-Transport-Security` in production
- `Content-Security-Policy` where compatible
- `Permissions-Policy`
- `Cache-Control: no-store` for authenticated financial responses where caching is not explicitly required
- consistent `X-Content-Type-Options` and frame protection

Target: headers are verified in an automated deployment smoke test.

#### P1.3 Shared rate limiting

SlowAPI currently uses process-local behavior unless a shared backend is configured. Multiple workers or instances can bypass effective limits.

Target: use Redis-backed limits keyed by a combination of user identity and IP, with separate budgets for authentication-adjacent, upload, export, AI, webhook, and mutation routes.

#### P1.4 Production error and API-surface hardening

- Disable or protect interactive `/docs` and `/redoc` in production.
- Never expose provider exception text, token-validation internals, SQL errors, or upstream response bodies.
- Add a request/correlation ID and structured security event logging.
- Ensure logs never contain bearer tokens, webhook secrets, receipt content, or full financial payloads.

#### P1.5 Google authentication lifecycle

Keep server-side Google verification as the source of truth. Add explicit checks for issuer, audience, expiry, subject, and verified email; reject malformed claims consistently. Move toward short-lived application sessions instead of replaying Google ID tokens on every API request.

### P2 — data protection and AI safety

#### P2.1 Data classification and retention

Document retention and deletion behavior for transactions, receipts, statement files, audit logs, notifications, AI conversations, caches, backups, and provider telemetry. Add scheduled deletion tests and a user-visible retention explanation.

#### P2.2 AI data minimization

- Send only fields necessary for the requested task.
- Make cloud AI opt-in for new users rather than backward-compatible default-on.
- Add provider-specific retention and region metadata to deployment configuration.
- Add tests that prove redaction before every provider adapter, including receipt and statement paths.
- Treat model output as untrusted data and keep deterministic evidence checks mandatory.

#### P2.3 Backup and export controls

- Require `BACKUP_ENCRYPTION_KEY` for production backup export/restore.
- Add key rotation and recovery documentation.
- Add export authorization audit events and re-authentication for restore/delete operations.
- Use a separate encryption key for each environment and never log encrypted backup tokens.

#### P2.4 Webhook security lifecycle

- Encrypt stored secrets.
- Add secret rotation and test delivery with the new secret before activation.
- Sign with timestamp plus body and reject replayed timestamps in the integration guidance.
- Keep SSRF validation at delivery time and add DNS-rebinding regression tests.

### P3 — secure engineering and operations

#### P3.1 Automated dependency and image scanning

Add CI gates for:

- `pip-audit` or equivalent Python dependency scanning
- `npm audit` with an explicit severity policy
- container image scanning
- secret scanning on commits and CI artifacts
- license review for production dependencies

#### P3.2 Security regression suite

Add tests for:

- cross-user access to every resource type
- expired, wrong-audience, wrong-issuer, malformed, and replayed tokens
- CORS origin rejection
- upload size, MIME, magic-byte, and decompression abuse
- SSRF variants: localhost, private IPv4/IPv6, metadata IPs, redirects, DNS rebinding, unusual ports
- webhook signature verification and replay handling
- prompt injection and sensitive-data redaction
- backup key failures and restore authorization

#### P3.3 Operational monitoring

Alert on:

- repeated authentication failures
- unusual export/delete/restore activity
- rate-limit exhaustion
- repeated webhook failures
- provider failures and AI budget exhaustion
- unexpected production configuration such as `AUTH_PROVIDER != google`
- database connection or migration failures

#### P3.4 Incident response

Document procedures for token compromise, webhook secret compromise, database exposure, provider data incident, malicious import, and accidental deletion. Include owner, containment action, credential rotation, user notification, evidence preservation, and recovery steps.

## Delivery phases and exit criteria

### Phase 0 — production baseline

- [x] Google-only authentication path for production.
- [x] Production rejects `AUTH_PROVIDER=dev`.
- [x] Supabase authentication path removed.
- [x] Non-root backend container.
- [x] Basic CORS and frontend security headers.
- [ ] Verify deployed environment variables and CORS origins against the real production domains.

Exit criteria: production starts only with Google auth, no Supabase dependency/reference remains, and a deployment smoke test confirms unauthorized requests receive 401.

### Phase 1 — identity and authorization

- [x] Move from localStorage bearer tokens to secure application sessions.
- [x] Complete strict Google claim validation tests.
- [ ] Build the two-user IDOR test matrix for every API route.
- [x] Add re-authentication for export, restore, and destructive profile operations.

Exit criteria: a stolen browser-readable token is no longer the normal session model, and the cross-user suite passes for all endpoints.

### Phase 2 — secrets, uploads, and API hardening

- [x] Encrypt webhook secrets and implement rotation.
- [x] Bound every upload read and validate content signatures before parsing.
- [x] Add authenticated response cache controls and API security headers.
- [x] Disable or protect production API documentation.
- [ ] Standardize safe error responses and correlation IDs.

Exit criteria: fuzzed uploads cannot exceed configured memory limits, secrets do not appear in DB exports/logs, and security headers are present on authenticated API responses.

### Phase 3 — abuse prevention and AI privacy

- [x] Move rate limits to shared Redis.
- [x] Separate limits by user and IP for expensive operations.
- [x] Make cloud AI opt-in for new accounts.
- [ ] Prove redaction at every provider boundary with tests. (Text router redaction and cloud opt-in for receipt and statement paths are tested; image/PDF content itself cannot be deterministically redacted before cloud OCR.)
- [x] Enforce production backup encryption configuration.

Exit criteria: abuse tests cannot bypass quotas by switching workers, sensitive fixtures are absent from provider-bound payloads, and backups fail closed without encryption configuration.

### Phase 4 — secure operations

- [x] Add dependency, image, secret, and license scanning to CI.
- [ ] Add security regression tests to required CI checks.
- [ ] Add production security alerts and a documented incident runbook. (Runbook added; alert wiring remains.)
- [ ] Perform an external penetration test focused on IDOR, auth, uploads, SSRF, and exports.

Exit criteria: all high-severity findings are closed or explicitly risk-accepted, CI blocks new critical/high vulnerabilities, and an incident drill is completed.

## Recommended execution order

1. Keep production Google-only and verify the deployed configuration.
2. Build the two-user authorization suite before adding more features.
3. Replace localStorage tokens with secure sessions.
4. Encrypt webhook secrets and bound all upload reads.
5. Harden headers, errors, docs, rate limits, backups, and AI defaults.
6. Add automated security scanning and complete an external review.

## Security definition of done

Ledger should not call a feature secure merely because it has authentication. A feature is security-complete only when it has:

- authenticated and authorized access;
- input, size, and content validation;
- safe failure behavior;
- privacy and retention behavior documented;
- auditability for sensitive mutations;
- abuse/rate-limit coverage;
- cross-user regression tests;
- deployment configuration validation; and
- an operational recovery path.
