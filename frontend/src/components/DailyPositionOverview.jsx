import React from "react";
import { apiFetch, money, formatDay } from "../lib";
import { useToast } from "./ui";

function Fact({ label, value, currency, hint, lead }) {
  return (
    <div style={{ minWidth: 0, padding: "16px 20px", borderLeft: "1px solid var(--border)" }} className="position-fact">
      <div style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: "20px" }}>{label}</div>
      <div className="num" style={{ color: value == null ? "var(--text-muted)" : lead ? "var(--primary)" : "var(--text-primary)", fontWeight: 500, fontSize: value == null ? 14 : 20, lineHeight: "28px", marginTop: 4 }}>
        {value == null ? "Not verified" : money(value, currency)}
      </div>
      {hint && <div style={{ color: "var(--text-muted)", fontSize: 12, lineHeight: "16px", marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

export default function DailyPositionOverview({ position, onReviewed, nextAction, onNavigate }) {
  const toast = useToast();
  const [showReview, setShowReview] = React.useState(false);
  const [confirmed, setConfirmed] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  if (!position) return null;
  if (position.error) return <div className="notice negative" role="alert" style={{ marginBottom: 16 }}>
    <span><strong>Today’s position could not load.</strong> {position.error}. Refresh before relying on these numbers.</span>
  </div>;

  const missingReview = position.reasons.some((reason) =>
    reason.startsWith("Confirm that this month's bills") || reason.startsWith("Review obligations again")
  );
  const upcoming = position.upcoming_obligations || [];
  const urgent = position.reasons.filter((reason) => !reason.startsWith("Variable future income"));
  const suggested = nextAction || (urgent.length
    ? { title: "Make this estimate reliable", reason: urgent[0], label: "Review accounts and budgets", run: () => onNavigate?.("accounts") }
    : null);

  async function completeReview(event) {
    event.preventDefault();
    if (!confirmed) return;
    setSaving(true);
    try {
      await apiFetch("/daily-position/review", { method: "POST", body: JSON.stringify({ confirmed: true }) });
      setShowReview(false);
      setConfirmed(false);
      await onReviewed?.();
      toast("Obligations review recorded", "success");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card position-card" aria-label="Today, this month, and next action" style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 500 }}>Today</h2>
          <span className="num" style={{ color: "var(--text-muted)", fontSize: 12 }}>{formatDay(position.as_of, { year: true })} · {position.currency}</span>
        </div>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "var(--text-secondary)", fontSize: 12 }}>
          <span className="status-dot" style={{ background: position.status === "ready" ? "var(--positive)" : "var(--warning)" }} aria-hidden="true" />
          {position.status === "ready" ? "Estimate available" : "Estimate withheld until data is reviewed"}
        </span>
      </div>
      <div className="position-grid">
        <Fact label="Safe to spend, estimate" value={position.safe_to_spend_estimate} currency={position.currency} hint="Future income excluded" lead />
        <Fact label="Cash across accounts" value={position.cash_available} currency={position.currency} hint="Fresh, reconciled cash accounts only" />
        <Fact label="Reserved to month end" value={position.reserve_remaining} currency={position.currency} hint="Remaining budgets and confirmed bills" />
        <Fact label="Income this month" value={position.income} currency={position.currency} />
        <Fact label="Committed spending" value={position.committed_spend} currency={position.currency} hint="Categories with confirmed recurring rules" />
        <Fact label="Flexible spending" value={position.flexible_spend} currency={position.currency} hint="All other categories" />
      </div>
      <div style={{ padding: "12px 20px 16px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 8, color: "var(--text-secondary)", fontSize: 13, lineHeight: "20px" }}>
        {upcoming.length > 0 && (
          <div>
            <span style={{ color: "var(--text-primary)" }}>Upcoming bills</span>{" · "}
            {upcoming.slice(0, 3).map((bill, i) => (
              <span key={`${bill.description}-${bill.due_date}`}>{i > 0 && " · "}{bill.description} <span className="num">{money(bill.amount, position.currency)}</span> on {formatDay(bill.due_date)}</span>
            ))}
            {upcoming.length > 3 ? ` · ${upcoming.length - 3} more` : ""}
          </div>
        )}
        {position.reasons.length > 0 && (
          <div><span style={{ color: "var(--text-primary)" }}>What affects this</span> · {position.reasons.join(" ")}</div>
        )}
        <div style={{ color: "var(--text-muted)", fontSize: 12 }}>{position.method}</div>
      </div>

      {suggested && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "16px 20px", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 320px" }}>
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 500 }}>Next action: {suggested.title}</h2>
            <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: 13, lineHeight: "20px" }}>{suggested.reason}</p>
          </div>
          <button type="button" className="btn-primary" onClick={suggested.run}>{suggested.label}</button>
        </div>
      )}
      {missingReview && (
        <div style={{ padding: "0 20px 16px" }}>
          <button type="button" className="btn-secondary" onClick={() => setShowReview((value) => !value)}>
            {showReview ? "Close obligations review" : "Review this month's obligations"}
          </button>
          {showReview && (
            <form onSubmit={completeReview} style={{ marginTop: 12, padding: 16, border: "1px solid var(--border)", borderRadius: 10 }}>
              <p style={{ margin: "0 0 12px", color: "var(--text-secondary)", fontSize: 13 }}>
                Review your budgets and confirmed recurring payments first. This confirmation expires after seven days or when those plans change.
              </p>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start", color: "var(--text-primary)", fontSize: 13 }}>
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                I have included all expected bills and planned spending for the rest of this month.
              </label>
              <button type="submit" className="btn-primary" style={{ marginTop: 12 }} disabled={!confirmed || saving}>
                {saving ? "Recording" : "Confirm my review"}
              </button>
            </form>
          )}
        </div>
      )}
    </section>
  );
}
