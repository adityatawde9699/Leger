import React from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "./ui";

function Fact({ label, value, currency, hint }) {
  return (
    <div style={{ minWidth: 150, flex: "1 1 160px" }}>
      <div style={{ color: "var(--text-muted)", fontSize: 12 }}>{label}</div>
      <div style={{ color: "var(--text-primary)", fontWeight: 750, fontSize: 19, marginTop: 4 }}>
        {value == null ? "Not verified" : money(value, currency)}
      </div>
      {hint && <div style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 3 }}>{hint}</div>}
    </div>
  );
}

export default function DailyPositionOverview({ position, onReviewed, nextAction, onNavigate }) {
  const toast = useToast();
  const [showReview, setShowReview] = React.useState(false);
  const [confirmed, setConfirmed] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  if (!position) return null;
  if (position.error) return <div className="card" role="alert" style={{ marginBottom: 24, padding: 20 }}>
    Today’s position could not load: {position.error}. Try refreshing before relying on these numbers.
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
    <section className="card" aria-label="Today, this month, and next action" style={{ marginBottom: 24, padding: 22 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 19 }}>Today</h2>
          <div style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 4 }}>As of {position.as_of} · {position.currency}</div>
        </div>
        <span style={{ color: position.status === "ready" ? "var(--positive)" : "var(--warning)", fontSize: 12, fontWeight: 700 }}>
          {position.status === "ready" ? "Estimate available" : "Estimate withheld until data is reviewed"}
        </span>
      </div>
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 20 }}>
        <Fact label="Observed cash across accounts" value={position.cash_available} currency={position.currency} hint="Only fresh, reconciled cash accounts" />
        <Fact label="Reserved through month-end" value={position.reserve_remaining} currency={position.currency} hint="Remaining budgets or confirmed bills" />
        <Fact label="Safe to spend · estimate" value={position.safe_to_spend_estimate} currency={position.currency} hint="Not your bank balance; future income excluded" />
      </div>
      {upcoming.length > 0 && (
        <div style={{ marginTop: 18, color: "var(--text-secondary)", fontSize: 13 }}>
          <strong style={{ color: "var(--text-primary)" }}>Upcoming confirmed obligations:</strong>{" "}
          {upcoming.slice(0, 3).map((bill) => `${bill.description} ${money(bill.amount, position.currency)} on ${bill.due_date}`).join(" · ")}
          {upcoming.length > 3 ? ` · ${upcoming.length - 3} more` : ""}
        </div>
      )}
      <div style={{ borderTop: "1px solid var(--border)", marginTop: 20, paddingTop: 18 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 17 }}>This month</h2>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
          <Fact label="Recorded income" value={position.income} currency={position.currency} />
          <Fact label="Committed-category spending" value={position.committed_spend} currency={position.currency} hint="Categories with confirmed recurring rules" />
          <Fact label="Flexible-category spending" value={position.flexible_spend} currency={position.currency} hint="All other expense categories" />
        </div>
      </div>
      {position.reasons.length > 0 && (
        <div style={{ marginTop: 18, color: "var(--text-secondary)", fontSize: 12, lineHeight: 1.6 }}>
          <strong>What affects this picture:</strong> {position.reasons.join(" ")}
        </div>
      )}
      <p style={{ color: "var(--text-muted)", fontSize: 11, lineHeight: 1.5, margin: "14px 0 0" }}>{position.method}</p>

      {suggested && (
        <div style={{ borderTop: "1px solid var(--border)", marginTop: 20, paddingTop: 18 }}>
          <h2 style={{ margin: "0 0 6px", fontSize: 17 }}>Next action: {suggested.title}</h2>
          <p style={{ margin: "0 0 12px", color: "var(--text-secondary)", fontSize: 13 }}>{suggested.reason}</p>
          <button type="button" className="btn-primary" onClick={suggested.run}>{suggested.label}</button>
        </div>
      )}
      {missingReview && (
        <div style={{ marginTop: 16 }}>
          <button type="button" className="btn-secondary" onClick={() => setShowReview((value) => !value)}>
            {showReview ? "Close obligations review" : "Review this month's obligations"}
          </button>
          {showReview && (
            <form onSubmit={completeReview} style={{ marginTop: 14, padding: 14, border: "1px solid var(--border)", borderRadius: 10 }}>
              <p style={{ margin: "0 0 10px", color: "var(--text-secondary)", fontSize: 13 }}>
                Review your budgets and confirmed recurring payments first. This confirmation expires after seven days or when those plans change.
              </p>
              <label style={{ display: "flex", gap: 9, alignItems: "flex-start", color: "var(--text-primary)", fontSize: 13 }}>
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                I have included all expected bills and planned spending for the rest of this month.
              </label>
              <button type="submit" className="btn-primary" style={{ marginTop: 12 }} disabled={!confirmed || saving}>
                {saving ? "Recording…" : "Confirm my review"}
              </button>
            </form>
          )}
        </div>
      )}
    </section>
  );
}
