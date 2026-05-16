# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| Latest `main` | ✅ Active |
| Previous releases | ⚠️ Critical fixes only |

## Reporting a Vulnerability

**Do NOT open a public issue for security vulnerabilities.**

Please report security issues responsibly:

1. **Email:** Send details to `security@your-domain.com`
2. **GitHub:** Use [GitHub's private vulnerability reporting](https://github.com/adityatawde9699/Leger/security/advisories/new)

### Include in Your Report

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

| Stage | Timeline |
|---|---|
| Acknowledgment | Within 48 hours |
| Initial assessment | Within 5 business days |
| Fix released | Within 30 days (critical: 7 days) |

## Security Architecture

### Authentication
- JWT-based authentication with multi-provider support (Supabase, Firebase)
- `AUTH_PROVIDER=dev` is **hard-blocked** in production environments
- All API endpoints require `Authorization: Bearer <token>` header

### Data Protection
- Financial data is stored locally by default (no cloud transmission)
- AI queries to cloud providers (Anthropic) contain anonymized context only
- Webhook secrets are HMAC-SHA256 signed
- Audit log provides immutable trail of all data mutations

### Input Validation
- Pydantic models validate all request payloads
- Prompt injection guard sanitizes AI inputs
- Rate limiting on all public endpoints via `slowapi`
- CORS restricted to configured origins only

### Dependencies
- Dependabot monitors for vulnerable dependencies weekly
- No `eval()`, `exec()`, or dynamic code execution
- SQL injection prevented via SQLAlchemy ORM (no raw queries)

## Disclosure Policy

We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure). After a fix is released, we will:

1. Credit the reporter (unless anonymity is requested)
2. Publish a security advisory on GitHub
3. Update the CHANGELOG with the fix
