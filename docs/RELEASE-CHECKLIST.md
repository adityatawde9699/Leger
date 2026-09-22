# Ledger release checklist

Use this checklist for every release that changes financial calculations, imports, or AI output.

## Automated gates

- [ ] `ruff check backend/`
- [ ] `pytest backend/tests/ -q`
- [ ] `npm ci` followed by `npm run build` in `frontend/`
- [ ] `git diff --check`
- [ ] `sh -n backend/entrypoint.sh` and the embedded migration syntax test

## Financial correctness

- [ ] Use `Decimal`/database numeric values for money; do not introduce binary-float arithmetic into persisted totals.
- [ ] Verify date range, inclusive/exclusive boundaries, timezone, and empty-history behavior.
- [ ] Verify currency display and calculation currency for every changed surface.
- [ ] Verify posted, pending, excluded, transfer, refund, and reimbursement semantics.
- [ ] Verify duplicate and partial-import behavior, including safe re-upload of the same statement.
- [ ] Verify incomplete history is labeled as insufficient rather than presented as complete.
- [ ] Verify every forecast, anomaly, insight, and advisor fact exposes its covered period and data sufficiency.

## AI and privacy

- [ ] Direct factual answers use deterministic Ledger calculations where available.
- [ ] Generated claims have valid evidence or are explicitly framed as uncertain.
- [ ] Provider, fallback, latency, parse, and evidence telemetry contains no raw financial text.
- [ ] No new cloud-AI path bypasses the configured provider/privacy behavior.
- [ ] Export and deletion behavior remains available and confirmation-gated.

## User experience

- [ ] Empty, loading, error, and partial-data states explain what the user can do next.
- [ ] Import review, correction, and undo paths remain reversible and auditable.
- [ ] Core mobile and keyboard flows are smoke-tested; color is not the only status signal.
