import React from "react";
import { apiFetch, money } from "../lib";
import { BarChart3, Info, Wallet } from "lucide-react";

function Period({ start, end, count }) {
  if (!count) return <span>No posted transactions yet</span>;
  return <span>Based on {count} posted transactions · {start} to {end}</span>;
}

function AmountCard({ label, value, currency }) {
  return (
    <div className="card" style={{ padding: 22 }}>
      <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, marginTop: 8 }}>
        {value === null ? "Not available" : money(value, currency)}
      </div>
    </div>
  );
}

export default function CreditBenchmarks() {
  const [tab, setTab] = React.useState("cash-flow");
  const [snapshot, setSnapshot] = React.useState(null);
  const [comparison, setComparison] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    Promise.all([apiFetch("/credit-health"), apiFetch("/benchmarks")])
      .then(([health, peers]) => {
        setSnapshot(health);
        setComparison(peers);
      })
      .catch((problem) => setError(problem.message || "Could not load your financial snapshot."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="view-credit">
      <h1 className="page-title">Your financial picture</h1>
      <p className="page-subtitle" style={{ marginBottom: 24 }}>
        Facts from your ledger, without an invented credit score or peer rank.
      </p>
      <div aria-label="Financial picture sections" style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <button type="button" aria-pressed={tab === "cash-flow"} onClick={() => setTab("cash-flow")}
          className="btn-secondary" style={{ opacity: tab === "cash-flow" ? 1 : 0.7 }}>
          <Wallet size={16} /> Cash flow
        </button>
        <button type="button" aria-pressed={tab === "peers"} onClick={() => setTab("peers")}
          className="btn-secondary" style={{ opacity: tab === "peers" ? 1 : 0.7 }}>
          <BarChart3 size={16} /> Peer comparison
        </button>
      </div>

      {loading && <div className="card" role="status">Loading your financial picture…</div>}
      {error && <div className="card" role="alert">{error}</div>}

      {!loading && !error && tab === "cash-flow" && snapshot && (
        <div role="region" aria-label="Cash-flow picture">
          <div className="card" style={{ padding: 22, marginBottom: 20 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <Info size={18} style={{ flexShrink: 0 }} />
              <div>
                <strong>Not a credit assessment</strong>
                <p style={{ margin: "6px 0 0", color: "var(--text-secondary)" }}>{snapshot.credit_reason}</p>
              </div>
            </div>
          </div>
          {snapshot.status === "currency_mismatch" ? (
            <div className="card" role="alert" style={{ padding: 22 }}>{snapshot.warnings[0]}</div>
          ) : (
            <>
              <p style={{ color: "var(--text-secondary)", marginBottom: 20 }}>
                <Period start={snapshot.period_start} end={snapshot.period_end} count={snapshot.transaction_count} />
              </p>
              <div className="account-grid">
                <AmountCard label="Recorded income" value={snapshot.income} currency={snapshot.currency} />
                <AmountCard label="Net spending" value={snapshot.expenses} currency={snapshot.currency} />
                <AmountCard label="Recorded cash flow" value={snapshot.net} currency={snapshot.currency} />
              </div>
              <div className="card" style={{ padding: 22, marginTop: 20 }}>
                <strong>Savings rate: {snapshot.savings_rate_pct === null ? "Not enough income data" : `${snapshot.savings_rate_pct}%`}</strong>
                <p style={{ margin: "8px 0 0", color: "var(--text-secondary)" }}>
                  {snapshot.savings_rate_pct === null
                    ? "Add income transactions before interpreting this rate."
                    : "Calculated as recorded income minus net spending, divided by recorded income over the period above."}
                </p>
              </div>
              {snapshot.warnings.length > 0 && (
                <div className="card" style={{ padding: 22, marginTop: 20 }}>
                  <strong>Before relying on this picture</strong>
                  <ul>{snapshot.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                </div>
              )}
              {snapshot.credit_readiness && snapshot.credit_readiness.status !== "unavailable" && (
                <div className="card" style={{ padding: 22, marginTop: 20 }}>
                  <strong>Recorded credit-account readiness</strong>
                  <p style={{ margin: "8px 0", color: "var(--text-secondary)" }}>{snapshot.credit_readiness.reason}</p>
                  {snapshot.credit_readiness.accounts.map((account) => (
                    <div key={account.account_id} style={{ borderTop: "1px solid var(--border)", padding: "10px 0", fontSize: 13 }}>
                      <strong>{account.name}</strong> · Owed {money(account.balance_owed, snapshot.currency)}
                      {account.utilization_pct === null ? " · Utilization unavailable" : ` · Utilization ${account.utilization_pct}%`}
                    </div>
                  ))}
                  {snapshot.credit_readiness.warnings?.length > 0 && <ul>{snapshot.credit_readiness.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
                  <p style={{ margin: "8px 0 0", color: "var(--text-muted)", fontSize: 11 }}>This is a record of the details you entered, not a lender or bureau assessment.</p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {!loading && !error && tab === "peers" && comparison && (
        <div role="region" aria-label="Peer comparison status">
          <div className="card" style={{ padding: 22, marginBottom: 20 }}>
            <strong>Peer ranking unavailable</strong>
            <p style={{ margin: "8px 0 0", color: "var(--text-secondary)" }}>{comparison.reason}</p>
          </div>
          {comparison.total_spending !== null && (
            <div className="card" style={{ padding: 22 }}>
              <h2 style={{ margin: "0 0 8px", fontSize: 18 }}>Your recorded spending</h2>
              <p style={{ color: "var(--text-secondary)", margin: "0 0 18px" }}>
                <Period start={comparison.period_start} end={comparison.period_end} count={comparison.transaction_count} />
              </p>
              <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 18 }}>{money(comparison.total_spending, comparison.currency)}</div>
              {comparison.categories.length === 0 ? (
                <p>No expenses recorded yet. Add or import transactions to see your category breakdown.</p>
              ) : comparison.categories.map((item) => (
                <div key={item.category} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "10px 0", borderTop: "1px solid var(--border)" }}>
                  <span>{item.category}</span><strong>{money(item.your_spend, comparison.currency)}</strong>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
