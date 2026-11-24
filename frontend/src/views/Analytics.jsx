import React from "react";
import { apiFetch, compactMoney, money, EXPENSE_CATEGORIES, formatDay, formatMonth, formatRange } from "../lib";
import { useToast } from "../components/ui";
import CurrencyMismatchNotice from "../components/CurrencyMismatchNotice";

import {
  BarChart, Bar, Cell, AreaChart, Area, LineChart, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend,
} from "recharts";

const TIME_FILTERS = [
  { id: "this_month",   label: "This month" },
  { id: "30d",          label: "30 days" },
  { id: "3m",           label: "3 months" },
  { id: "current_year", label: "This year" },
  { id: "all",          label: "All time" },
];

// One accent per chart; everything else in neutral steps of the ramp.
const INK = { accent: "#b6e35a", neutral: "#5c5c62", neutralLight: "#85858b", grid: "rgba(237,237,237,0.06)" };
const AXIS = { fontSize: 11, fill: "#85858b", fontFamily: "IBM Plex Mono, monospace" };
const SEVERITY_LABEL = { high: "High", medium: "Medium", low: "Low" };


function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--surface-secondary)", border: "1px solid var(--border-hover)", borderRadius: 8, padding: "8px 12px", boxShadow: "var(--shadow-float)" }}>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
          <span className="status-dot" style={{ background: p.color || p.stroke }} />
          <span style={{ flex: 1 }}>{p.name || p.dataKey}</span>
          <span className="num" style={{ color: "var(--text-primary)" }}>{money(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function Analytics({ onNavigate }) {
  const toast = useToast();
  const [timeRange,  setTimeRange]  = React.useState("3m");
  const [summary,    setSummary]    = React.useState(null);
  const [anomalies,  setAnomalies]  = React.useState([]);
  const [forecast,   setForecast]   = React.useState(null);
  const [runway,     setRunway]     = React.useState(null);
  const [leakage,    setLeakage]    = React.useState(null);
  const [comparison, setComparison] = React.useState(null);
  const [comparisonMode, setComparisonMode] = React.useState("mom");
  const [loading,    setLoading]    = React.useState(true);
  const [scenario,   setScenario]   = React.useState(null);
  const [anomalyFeedback, setAnomalyFeedback] = React.useState({});
  const [scenarioForm, setScenarioForm] = React.useState({ scenario_type: "category_reduction", category: "Dining", reduction_pct: 20, income_change_pct: 0, one_time_expense: 0, target_amount: 0, horizon_months: 1 });
  const [scenarioLoading, setScenarioLoading] = React.useState(false);

  const sendAnomalyFeedback = async (anomaly, feedback) => {
    if (!anomaly.id || anomalyFeedback[anomaly.id]) return;
    setAnomalyFeedback((current) => ({ ...current, [anomaly.id]: feedback }));
    try {
      await apiFetch("/insights/feedback", {
        method: "POST",
        body: JSON.stringify({ insight_id: anomaly.id, feedback }),
      });
    } catch (error) {
      setAnomalyFeedback((current) => {
        const next = { ...current };
        delete next[anomaly.id];
        return next;
      });
      toast(error.message, "error");
    }
  };

  React.useEffect(() => {
    setLoading(true);
    Promise.all([
      apiFetch(`/summary?range=${timeRange}`),
      apiFetch(`/analytics/anomalies?range=${timeRange}`).catch(() => []),
      apiFetch(`/analytics/forecast`).catch(() => null),
      apiFetch(`/analytics/runway?horizon_months=3`).catch(() => null),
      apiFetch(`/analytics/leakage`).catch(() => null),
      apiFetch(`/analytics/compare?comparison=${comparisonMode}`).catch(() => null),
    ]).then(([s, a, f, r, l, c]) => {
      setSummary(s);
      setAnomalies(Array.isArray(a) ? a : []);
      setForecast(f);
      setRunway(r);
      setLeakage(l);
      setComparison(c);
    }).catch(e => toast(e.message, "error"))
      .finally(() => setLoading(false));
  }, [timeRange, comparisonMode]);

  if (loading) {
    return (
      <div style={{ padding: "32px 0" }}>
        <h1 className="page-title" style={{ marginBottom: 6 }}>Analytics</h1>
        <p className="page-subtitle">Loading analytics data</p>
        <div className="charts-grid" style={{ marginTop: 24 }}>
          {[1,2,3,4].map(i => (
            <div key={i} className="card skeleton" style={{ height: 240 }} />
          ))}
        </div>
      </div>
    );
  }

  if (summary?.data_quality?.currency_mismatch_count > 0) {
    return <CurrencyMismatchNotice title="Analytics" onNavigate={onNavigate} />;
  }

  // ── Data preparation ────────────────────────────────────────────────────────
  const byCategory = summary?.by_category || {};
  const byMonth    = summary?.by_month    || {};
  const byDay      = summary?.by_day      || {};

  // Month-over-month comparison table
  const months = Object.keys(byMonth).sort();
  const momRows = months.slice(1).map((month, i) => {
    const curr = byMonth[month]    || { income: 0, expenses: 0 };
    const prev = byMonth[months[i]] || { income: 0, expenses: 0 };
    const currExp  = Number(curr.expenses);
    const prevExp  = Number(prev.expenses);
    const delta    = prevExp > 0 ? ((currExp - prevExp) / prevExp) * 100 : 0;
    const currInc  = Number(curr.income);
    const prevInc  = Number(prev.income);
    const incDelta = prevInc > 0 ? ((currInc - prevInc) / prevInc) * 100 : 0;
    return { month, currExp, prevExp, delta, currInc, prevInc, incDelta };
  });

  // Rolling 90-day spending by category (top 6)
  const topCats = Object.entries(byCategory)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 6)
    .map(([cat]) => cat);

  // Category spending timeline (by month)
  const catTimeline = months.map(month => {
    const row = { month };
    // We only have aggregate by_month, so use by_category totals as single bars
    topCats.forEach(cat => { row[cat] = byCategory[cat] ? Number(byCategory[cat]) : 0; });
    return row;
  });

  // Spending heatmap: day × category intensity
  const heatmapData = topCats.map((cat) => {
    const catTotal = Number(byCategory[cat] || 0);
    return { category: cat, value: catTotal };
  }).sort((a, b) => b.value - a.value);

  // Monthly cash flow with net line
  const cashFlowData = months.map(month => {
    const row = byMonth[month] || { income: 0, expenses: 0 };
    return {
      month,
      Income:   Number(row.income),
      Expenses: Number(row.expenses),
      Net:      Number(row.income) - Number(row.expenses),
    };
  });

  // Anomaly timeline
  const anomalyByDate = anomalies.reduce((acc, a) => {
    acc[a.date] = (acc[a.date] || 0) + 1;
    return acc;
  }, {});
  const anomalyTimeline = Object.entries(anomalyByDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({ date: formatDay(date), count }));

  // Forecast bars for top categories
  const forecastBars = forecast?.by_category
    ? Object.entries(forecast.by_category)
        .map(([cat, proj]) => ({
          cat,
          "Current":    Math.round(Number(byCategory[cat] || 0)),
          "30-Day Proj": Math.round(proj.projected_30d),
          "90-Day Proj": Math.round(proj.projected_90d),
          trend:         proj.trend,
          confidence:    proj.confidence,
        }))
        .filter(r => r["Current"] > 0 || r["30-Day Proj"] > 0)
        .sort((a, b) => b["30-Day Proj"] - a["30-Day Proj"])
        .slice(0, 8)
    : [];

  const income   = Number(summary?.income   || 0);
  const expenses = Number(summary?.expenses || 0);
  const net      = income - expenses;
  const months_covered = summary?.months_covered || 1;
  const avgMonthlyExpense = expenses / months_covered;
  const scenarioCategories = [...new Set([...EXPENSE_CATEGORIES, ...Object.keys(byCategory)])];

  async function runScenario(e) {
    e.preventDefault();
    setScenarioLoading(true);
    try {
      const result = await apiFetch("/analytics/scenario", {
        method: "POST",
        body: JSON.stringify({
          ...scenarioForm,
          reduction_pct: Number(scenarioForm.reduction_pct) || 0,
          income_change_pct: Number(scenarioForm.income_change_pct) || 0,
          one_time_expense: Number(scenarioForm.one_time_expense) || 0,
          horizon_months: Number(scenarioForm.horizon_months) || 1,
        }),
      });
      setScenario(result);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setScenarioLoading(false);
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <p className="page-subtitle" style={{ fontFamily: "var(--font-display)", fontSize: 14, color: "var(--text-secondary)" }}>
            Spending patterns, forecasts and unusual activity
          </p>
        </div>
        <div className="segmented" role="group" aria-label="Period">
          {TIME_FILTERS.map(r => (
            <button key={r.id} type="button" aria-pressed={timeRange === r.id} onClick={() => setTimeRange(r.id)}>{r.label}</button>
          ))}
        </div>
      </div>

      {/* KPI Row */}
      <div className="account-grid kpi-grid" style={{ marginBottom: 24 }}>
        {[
          { label: "Average monthly spending", val: money(avgMonthlyExpense), sub: `Over ${months_covered} month${months_covered === 1 ? "" : "s"}` },
          { label: "Income",                   val: money(income),           sub: summary?.period_start && summary?.period_end ? formatRange(summary.period_start, summary.period_end) : "All time" },
          { label: "Saved",                    val: money(Math.max(0, net)), sub: income > 0 ? `${Math.round((Math.max(0,net)/income)*100)}% of income` : "No income recorded", accent: net > 0 },
          { label: "Unusual transactions",     val: String(anomalies.length), sub: `${anomalies.filter(a=>a.severity==="high").length} high severity` },
        ].map(({ label, val, sub, accent }) => (
          <div key={label} className="card account-card">
            <div className="account-card-header"><span className="account-label">{label}</span></div>
            <div className="account-amount" style={accent ? { color: "var(--primary)" } : undefined}>{val}</div>
            <div className="account-change muted">{sub}</div>
          </div>
        ))}
      </div>

      {/* Evidence-backed same-length comparison */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="chart-card-header">
          <div>
            <div className="chart-title">{comparisonMode === "yoy" ? "This month vs same month last year" : "This month vs previous month"}</div>
            <div className="chart-subtitle">
              {comparison?.status === "ready"
                ? `${formatRange(comparison.current.period.start, comparison.current.period.end)} compared with ${formatRange(comparison.previous.period.start, comparison.previous.period.end)}`
                : comparison?.data_quality?.warnings?.join(" · ") || "Not enough history for a trustworthy comparison."}
            </div>
          </div>
          <select className="premium-select" value={comparisonMode} onChange={(e) => setComparisonMode(e.target.value)} aria-label="Comparison period">
            <option value="mom">Month over month</option>
            <option value="yoy">Year over year</option>
          </select>
        </div>
        {comparison?.status === "ready" ? (
          <div className="account-grid" style={{ marginBottom: 0 }}>
            {[
              ["Spending change", comparison.changes.expenses, comparison.changes.expenses_percent, "var(--negative)"],
              ["Income change", comparison.changes.income, comparison.changes.income_percent, "var(--positive)"],
              ["Net cash-flow change", comparison.changes.net, comparison.changes.net_percent, "var(--info)"],
            ].map(([label, change, percent, color]) => (
              <div key={label} style={{ padding: "4px 0" }}>
                <div className="account-label">{label}</div>
                <div style={{ fontSize: 20, fontWeight: 500, color }}>{Number(change) >= 0 ? "+" : ""}{money(change)}</div>
                <div className="muted" style={{ fontSize: 12 }}>{percent == null ? "No prior baseline" : `${Number(percent) >= 0 ? "+" : ""}${percent}%`}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state" style={{ padding: "8px 0 0" }}>Add transactions across two comparable periods to unlock trend analysis.</div>
        )}
      </div>

      {/* Fixed versus flexible spending from confirmed obligation evidence. */}
      {summary?.analysis?.fixed_flexible && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Committed vs flexible spending</div>
              <div className="chart-subtitle">Only confirmed recurring rules count as committed; unmatched transactions stay flexible.</div>
            </div>
          </div>
          {summary.analysis.fixed_flexible.status === "insufficient_data" ? (
            <div className="empty-state" style={{ padding: "8px 0 0" }}>
              {summary.analysis.fixed_flexible.data_quality.warnings.join(" ")}
            </div>
          ) : (
            <>
              <div className="account-grid" style={{ marginBottom: 0 }}>
                {[
                  ["Committed", summary.analysis.fixed_flexible.fixed_amount, "var(--warning)"],
                  ["Flexible", summary.analysis.fixed_flexible.flexible_amount, "var(--info)"],
                ].map(([label, value, color]) => (
                  <div key={label} style={{ padding: "4px 0" }}>
                    <div className="account-label">{label}</div>
                    <div style={{ fontSize: 20, fontWeight: 500, color }}>{money(value)}</div>
                  </div>
                ))}
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>
                {summary.analysis.fixed_flexible.confirmed_rule_count} confirmed obligation rule{summary.analysis.fixed_flexible.confirmed_rule_count === 1 ? "" : "s"}; amounts link back to posted transaction evidence.
              </div>
            </>
          )}
        </div>
      )}

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="chart-card-header">
          <div>
            <div className="chart-title">Cash-flow runway</div>
            <div className="chart-subtitle">A deterministic projection from reconciled cash, posted spending, and confirmed obligations.</div>
          </div>
        </div>
        {runway?.status !== "ready" ? (
          <div className="empty-state" style={{ padding: "8px 0 0" }}>
            {runway?.data_quality?.warnings?.join(" ") || "Reconcile a cash account and add posted history before relying on runway."}
          </div>
        ) : (
          <>
            <div className="account-grid" style={{ marginBottom: 0 }}>
              {[
                ["Starting reconciled cash", runway.starting_cash, "var(--text-primary)"],
                ["Monthly obligations", runway.fixed_monthly_obligations, "var(--warning)"],
                ["Monthly flexible spend", runway.flexible_monthly_spend, "var(--info)"],
              ].map(([label, value, color]) => (
                <div key={label} style={{ padding: "4px 0" }}>
                  <div className="account-label">{label}</div>
                  <div style={{ fontSize: 19, fontWeight: 500, color }}>{money(value)}</div>
                </div>
              ))}
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.5 }}>
              Income assumption: {money(runway.income_assumption.low)}–{money(runway.income_assumption.high)} per month. {runway.income_assumption.method}. Future income is not guaranteed.
            </div>
            {runway.data_quality.warnings?.length > 0 && (
              <div style={{ color: "var(--warning)", fontSize: 12, marginTop: 8 }}>{runway.data_quality.warnings.join(" ")}</div>
            )}
          </>
        )}
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="chart-card-header">
          <div>
            <div className="chart-title">Review possible leakage</div>
            <div className="chart-subtitle">Candidates from your own transaction and confirmed recurring-payment history.</div>
          </div>
        </div>
        {leakage?.status !== "ready" ? (
          <div className="empty-state" style={{ padding: "8px 0 0" }}>
            {leakage?.data_quality?.warnings?.join(" ") || "Add posted history before checking for possible leakage."}
          </div>
        ) : leakage.items?.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {leakage.items.slice(0, 5).map((item) => (
              <div key={item.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ color: "var(--text-primary)", fontWeight: 500, fontSize: 13 }}>{item.claim}</div>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{item.recommended_action} Confidence: {item.confidence}.</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state" style={{ padding: "8px 0 0" }}>Nothing notable in the available history. Ledger will show candidates only when evidence supports a review.</div>
        )}
      </div>

      {/* Deterministic scenario planner */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="chart-card-header">
          <div>
            <div className="chart-title">Scenario planner</div>
            <div className="chart-subtitle">See the monthly effect of a change using your last 90 days of transactions. No AI estimates.</div>
          </div>
        </div>
        <form onSubmit={runScenario}>
          <div className="form-grid-2">
            <div className="form-field">
              <label className="form-label">Scenario type</label>
              <select value={scenarioForm.scenario_type} onChange={e => setScenarioForm({ ...scenarioForm, scenario_type: e.target.value })}>
                <option value="category_reduction">Reduce a category</option>
                <option value="purchase">Plan a one-time purchase</option>
                <option value="income_shock">Model an income change</option>
                <option value="savings_target">Reach a savings target</option>
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">Category to reduce</label>
              <select value={scenarioForm.category} onChange={e => setScenarioForm({ ...scenarioForm, category: e.target.value })}>
                {scenarioCategories.map(cat => <option key={cat} value={cat}>{cat}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">Reduction (%)</label>
              <input type="number" min="0" max="100" step="1" value={scenarioForm.reduction_pct}
                onChange={e => setScenarioForm({ ...scenarioForm, reduction_pct: e.target.value })} />
            </div>
            <div className="form-field">
              <label className="form-label">Income change (%)</label>
              <input type="number" min="-100" max="100" step="1" value={scenarioForm.income_change_pct}
                onChange={e => setScenarioForm({ ...scenarioForm, income_change_pct: e.target.value })} />
            </div>
            <div className="form-field">
              <label className="form-label">One-time expense</label>
              <input type="number" min="0" step="100" value={scenarioForm.one_time_expense}
                onChange={e => setScenarioForm({ ...scenarioForm, one_time_expense: e.target.value })} />
            </div>
            {scenarioForm.scenario_type === "savings_target" && <div className="form-field">
              <label className="form-label">Savings target</label>
              <input type="number" min="0" step="100" value={scenarioForm.target_amount}
                onChange={e => setScenarioForm({ ...scenarioForm, target_amount: e.target.value })} />
            </div>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 4 }}>
            <button type="submit" className="btn-primary" disabled={scenarioLoading}>{scenarioLoading ? "Calculating…" : "Calculate scenario"}</button>
            <label className="form-label" style={{ margin: 0 }}>Over
              <select style={{ marginLeft: 8 }} value={scenarioForm.horizon_months} onChange={e => setScenarioForm({ ...scenarioForm, horizon_months: e.target.value })}>
                {[1, 3, 6, 12].map(n => <option key={n} value={n}>{n} month{n > 1 ? "s" : ""}</option>)}
              </select>
            </label>
          </div>
        </form>
        {scenario && (
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
              Based on {scenario.transaction_count} transactions from {scenario.period_start || "no recorded history"} to {scenario.period_end || "today"}.
            </div>
            <div className="account-grid">
              {[
                ["Current monthly net", scenario.baseline_monthly_net, "var(--text-secondary)"],
                ["Projected monthly net", scenario.projected_monthly_net, scenario.projected_monthly_net >= 0 ? "var(--positive)" : "var(--negative)"],
                ["Monthly improvement", Number(scenario.monthly_savings) + (Number(scenario.projected_monthly_income) - Number(scenario.baseline_monthly_income)), "var(--info)"],
                [`${scenario.horizon_months}-month net change`, scenario.horizon_net_change, scenario.horizon_net_change >= 0 ? "var(--positive)" : "var(--negative)"],
              ].map(([label, value, color]) => (
                <div key={label} style={{ padding: "12px 16px", borderRadius: 12, background: "var(--surface-secondary)" }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
                  <div style={{ fontSize: 18, fontWeight: 500, color }}>{money(value)}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>
              Category baseline: {money(scenario.category_monthly_spend)}/month · First month after one-time expense: {money(scenario.first_month_net_after_one_time)} · Observed coverage: {scenario.data_quality?.coverage || "unknown"}.
              {scenario.scenario_type === "savings_target" && ` Required monthly saving: ${money(scenario.required_monthly_saving)} · Target ${scenario.target_feasible ? "appears feasible" : "needs a larger margin"} based on observed history.`}
            </div>
          </div>
        )}
      </div>

      {/* Monthly Cash Flow Trend */}
      {cashFlowData.length > 1 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Monthly cash flow</div>
              <div className="chart-subtitle">Income vs expenses vs net across all months</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={cashFlowData}>
              <defs>
                <linearGradient id="gAnalyticsInc" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"  stopColor={INK.accent} stopOpacity={0.14} />
                  <stop offset="100%" stopColor={INK.accent} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gAnalyticsExp" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"  stopColor={INK.neutralLight} stopOpacity={0} />
                  <stop offset="100%" stopColor={INK.neutralLight} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey="month" tick={AXIS} axisLine={false} tickLine={false} tickFormatter={(m) => formatMonth(m, { year: false })} dy={8} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} width={62}
                tickFormatter={compactMoney} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="Income"   name="Income"   stroke={INK.accent} fill="url(#gAnalyticsInc)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="Expenses" name="Spending" stroke={INK.neutralLight} fill="url(#gAnalyticsExp)" strokeWidth={1.5} dot={false} />
              <Line type="monotone" dataKey="Net"      name="Net"      stroke={INK.neutral} strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Month-over-Month Comparison */}
      {momRows.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Month over month</div>
              <div className="chart-subtitle">Spending change vs previous month</div>
            </div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Month", "Income", "ΔIncome", "Expenses", "ΔSpend", "Net"].map(h => (
                    <th key={h} style={{ padding: "10px 16px", textAlign: h === "Month" ? "left" : "right", color: "var(--text-muted)", fontWeight: 500, fontSize: 11 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {momRows.map((row, i) => (
                  <tr key={row.month} style={{ borderBottom: "1px solid var(--border)", }}>
                    <td style={{ padding: "12px 16px", fontWeight: 400, color: "var(--text-primary)" }}>{formatMonth(row.month)}</td>
                    <td style={{ padding: "12px 16px", textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 400 }}>{money(row.currInc)}</td>
                    <td style={{ padding: "12px 16px", textAlign: "right" }}>
                      <span style={{ color: row.incDelta >= 0 ? "var(--positive)" : "var(--negative)", fontWeight: 500, fontSize: 12 }}>
                        {row.incDelta >= 0 ? "↑" : "↓"}{Math.abs(row.incDelta).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 400 }}>{money(row.currExp)}</td>
                    <td style={{ padding: "12px 16px", textAlign: "right" }}>
                      <span style={{
                        color: row.delta <= 0 ? "var(--positive)" : "var(--negative)",
                        background: row.delta <= 0 ? "var(--positive-soft)" : "var(--negative-soft)",
                        padding: "2px 8px", borderRadius: 8, fontWeight: 500, fontSize: 12,
                      }}>
                        {row.delta >= 0 ? "↑" : "↓"}{Math.abs(row.delta).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: 500, color: row.currInc - row.currExp >= 0 ? "var(--positive)" : "var(--negative)" }}>
                      {money(row.currInc - row.currExp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Spending Heatmap by Category */}
      {heatmapData.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Spending intensity by category</div>
              <div className="chart-subtitle">Relative spending intensity per category</div>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
            {heatmapData.map((item) => {
              const maxVal  = heatmapData[0]?.value || 1;
              const opacity = 0.15 + (item.value / maxVal) * 0.85;
              return (
                <div key={item.category} style={{
                  padding: 12, borderRadius: 10,
                  background: `rgba(237,237,237,${(0.02 + opacity * 0.06).toFixed(3)})`,
                  border: "1px solid var(--border)",
                }}>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
                    {item.category}
                  </div>
                  <div className="num" style={{ fontSize: 15, fontWeight: 500, color: "var(--text-primary)" }}>
                    {money(item.value)}
                  </div>
                  <div style={{ marginTop: 8, height: 2, borderRadius: 1, background: "var(--surface-secondary)", overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 1,
                      width: `${(item.value / maxVal) * 100}%`,
                      background: item.value === maxVal ? "var(--primary)" : "var(--text-muted)",
                    }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Forecast vs Actual */}
      {forecastBars.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Forecast against actual</div>
              <div className="chart-subtitle">EWMA projection, 30 and 90 days ahead per category</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={forecastBars} barGap={3} barCategoryGap="25%" margin={{ top: 5, right: 28, bottom: 5, left: 0 }}>
              <CartesianGrid stroke={INK.grid} vertical={false} />
              <XAxis dataKey="cat" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} width={64}
                tickFormatter={compactMoney} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="Current"     fill={INK.neutral} radius={[2,2,0,0]} maxBarSize={16} />
              <Bar dataKey="30-Day Proj" name="Next 30 days" fill={INK.accent} radius={[2,2,0,0]} maxBarSize={16} />
              <Bar dataKey="90-Day Proj" name="Next 90 days" fill={INK.neutralLight} radius={[2,2,0,0]} maxBarSize={16} />
            </BarChart>
          </ResponsiveContainer>
          {/* Trend indicators */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            {forecastBars.map(r => (
              <div key={r.cat} style={{ fontSize: 12, color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: 6, marginRight: 8 }}>
                <span className="status-dot" style={{ background: r.trend === "up" ? "var(--negative)" : r.trend === "down" ? "var(--positive)" : "var(--text-muted)" }} aria-hidden="true" />
                <span style={{ color: "var(--text-secondary)" }}>{r.cat}</span> {r.trend === "up" ? "rising" : r.trend === "down" ? "falling" : "stable"}
                <span className="num">{Math.round(r.confidence * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Anomaly Timeline */}
      {anomalies.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Unusual activity over time</div>
              <div className="chart-subtitle">{anomalies.length} unusual transactions detected</div>
            </div>
          </div>

          {anomalyTimeline.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <ResponsiveContainer width="100%" height={80}>
                <BarChart data={anomalyTimeline}>
                  <XAxis dataKey="date" tick={AXIS} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(v) => [`${v} unusual transaction${v !== 1 ? "s" : ""}`, ""]}
                    separator=""
                    cursor={{ fill: "rgba(237,237,237,0.04)" }}
                    contentStyle={{ background: "var(--surface-secondary)", border: "1px solid var(--border-hover)", borderRadius: 8, fontSize: 13 }}
                    labelStyle={{ color: "var(--text-muted)", fontSize: 12 }}
                    itemStyle={{ color: "var(--text-primary)" }}
                  />
                  <Bar dataKey="count" name="Unusual" fill={INK.neutralLight} radius={[2,2,0,0]} maxBarSize={12} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {anomalies.slice(0, 10).map((a) => (
              <div key={a.transaction_id} style={{
                display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
                borderRadius: 12, border: "1px solid var(--border)",
                background: "var(--surface)",
              }}>
                <span className={`status-dot ${a.severity}`} aria-hidden="true" />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>{a.message}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                    {a.category} · <span className="num">{money(a.amount)}</span> · {formatDay(a.date, { year: true })}
                    {a.expected_range && ` · Normal: ${money(a.expected_range.min)}–${money(a.expected_range.max)}`}
                  </div>
                  {a.analysis?.method && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                      Method: {a.analysis.method} · {a.recommended_action}
                    </div>
                  )}
                </div>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {SEVERITY_LABEL[a.severity] || a.severity}
                </span>
                <button className="btn-link" type="button" onClick={() => onNavigate?.("transactions")} style={{ fontSize: 11, padding: 0 }}>
                  Review transaction
                </button>
                <div style={{ display: "flex", gap: 4, flexDirection: "column" }}>
                  {anomalyFeedback[a.id] ? (
                    <span className="muted" style={{ fontSize: 11 }}>Recorded</span>
                  ) : (
                    <>
                      <button className="btn-secondary btn-sm" onClick={() => sendAnomalyFeedback(a, "helpful")}>Useful</button>
                      <button className="btn-secondary btn-sm" onClick={() => sendAnomalyFeedback(a, "inaccurate")}>Not accurate</button>
                    </>
                  )}
                </div>
              </div>
            ))}
            {anomalies.length > 10 && (
              <div style={{ fontSize: 13, color: "var(--text-muted)", textAlign: "center", padding: "8px 0" }}>
                + {anomalies.length - 10} more anomalies · Showing top 10
              </div>
            )}
          </div>
        </div>
      )}

      {/* Category Breakdown Bar Chart */}
      {Object.keys(byCategory).length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Spending by category</div>
              <div className="chart-subtitle">Total spend per category this period</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              layout="vertical"
              data={Object.entries(byCategory)
                .map(([cat, val]) => ({ cat, value: Number(val) }))
                .sort((a,b) => b.value - a.value)
                .slice(0, 10)}
              margin={{ left: 20, right: 30 }}
            >
              <CartesianGrid stroke={INK.grid} horizontal={false} />
              <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false}
                tickFormatter={compactMoney} />
              <YAxis type="category" dataKey="cat" tick={{ fontSize: 12, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} width={90} />
              <Tooltip
                formatter={v => [money(v), "Spend"]}
                content={<ChartTooltip />}
              />
              <Bar dataKey="value" name="Spending" radius={[0,2,2,0]} maxBarSize={14}>
                {Object.entries(byCategory)
                  .sort((a,b) => Number(b[1]) - Number(a[1]))
                  .slice(0,10)
                  .map(([cat], i) => <Cell key={cat} fill={i === 0 ? INK.accent : INK.neutral} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
