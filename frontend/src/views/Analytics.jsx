import React from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, money, EXPENSE_CATEGORIES, CATEGORY_COLORS, paletteColor, KEYS } from "../lib";
import { QueryGate } from "../components/ui";
import { AlertTriangle, TrendingUp, TrendingDown, BarChart3, Activity, Zap } from "lucide-react";
import {
  BarChart, Bar, Cell, AreaChart, Area, LineChart, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend,
} from "recharts";

const TIME_FILTERS = [
  { id: "3m",          label: "3 Months"  },
  { id: "current_year",label: "This Year" },
  { id: "all",         label: "All Time"  },
];

const SEVERITY_COLOR = { high: "var(--negative)", medium: "var(--warning)", low: "var(--info)" };

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "12px 16px", boxShadow: "var(--shadow)" }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600, color: p.color, marginBottom: 4 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: p.color }} />
          {p.name || p.dataKey}: {money(p.value)}
        </div>
      ))}
    </div>
  );
}

export default function Analytics() {
  const [timeRange,  setTimeRange]  = React.useState("3m");

  const summaryQuery = useQuery({
    queryKey: KEYS.summary(timeRange),
    queryFn: () => apiFetch(`/summary?range=${timeRange}`),
  });
  const { data: anomaliesData } = useQuery({
    queryKey: KEYS.anomalies(timeRange),
    queryFn: () => apiFetch(`/analytics/anomalies?range=${timeRange}`),
  });
  const { data: forecast } = useQuery({
    queryKey: KEYS.forecast(),
    queryFn: () => apiFetch(`/analytics/forecast`),
  });

  const summary = summaryQuery.data;
  const anomalies = Array.isArray(anomaliesData) ? anomaliesData : [];

  const skeleton = (
    <div style={{ padding: "32px 0" }}>
      <h1 className="page-title" style={{ marginBottom: 6 }}>Analytics</h1>
      <p className="page-subtitle">Loading analytics data…</p>
      <div className="charts-grid" style={{ marginTop: 24 }}>
        {[1,2,3,4].map(i => (
          <div key={i} className="card skeleton" style={{ height: 240 }} />
        ))}
      </div>
    </div>
  );

  if (summaryQuery.isLoading || summaryQuery.isError) {
    return (
      <QueryGate
        loading={summaryQuery.isLoading}
        error={summaryQuery.error}
        onRetry={summaryQuery.refetch}
        skeleton={skeleton}
      />
    );
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
  const heatmapData = topCats.map((cat, i) => {
    const catTotal = Number(byCategory[cat] || 0);
    const norm = cat.charAt(0).toUpperCase() + cat.slice(1).toLowerCase();
    const color = CATEGORY_COLORS[norm] || CATEGORY_COLORS[cat] || paletteColor(cat, i);
    return { category: cat, value: catTotal, color };
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
    .map(([date, count]) => ({ date: date.slice(5), count }));

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

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 16, marginBottom: 32 }}>
        <div>
          <h1 className="page-title" style={{ marginBottom: 6 }}>Analytics</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>
            Deep dive into spending patterns, forecasts, and anomalies
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {TIME_FILTERS.map(r => (
            <button key={r.id}
              onClick={() => setTimeRange(r.id)}
              className={timeRange === r.id ? "btn-primary" : "btn-secondary"}
              style={{ padding: "8px 16px", fontSize: 13 }}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Row */}
      <div className="account-grid" style={{ marginBottom: 24 }}>
        {[
          { label: "Avg Monthly Spend", val: money(avgMonthlyExpense), sub: `over ${months_covered} month(s)`, color: "var(--negative)", Icon: TrendingDown },
          { label: "Total Income",       val: money(income),           sub: summary?.period_start ? `${summary.period_start} →` : "All time", color: "var(--positive)", Icon: TrendingUp },
          { label: "Net Savings",        val: money(Math.max(0, net)), sub: income > 0 ? `${Math.round((Math.max(0,net)/income)*100)}% rate` : "—",  color: "var(--info)", Icon: Activity },
          { label: "Anomalies",          val: anomalies.length,        sub: `${anomalies.filter(a=>a.severity==="high").length} high severity`, color: "var(--warning)", Icon: AlertTriangle, isCount: true },
        ].map(({ label, val, sub, color, Icon, isCount }) => (
          <div key={label} className="card account-card" style={{ borderTop: `3px solid ${color}` }}>
            <div className="account-card-header">
              <span className="account-label">{label}</span>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}18`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon size={18} style={{ color }} />
              </div>
            </div>
            <div className="account-amount" style={{ fontSize: isCount ? 28 : 22 }}>{val}</div>
            <div className="account-change muted" style={{ fontSize: 12 }}>{sub}</div>
          </div>
        ))}
      </div>

      {/* Monthly Cash Flow Trend */}
      {cashFlowData.length > 1 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Monthly Cash Flow Trend</div>
              <div className="chart-subtitle">Income vs expenses vs net across all months</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={cashFlowData}>
              <defs>
                <linearGradient id="gAnalyticsInc" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="var(--positive)" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="var(--positive)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gAnalyticsExp" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="var(--negative)" stopOpacity={0.12} />
                  <stop offset="95%" stopColor="var(--negative)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-secondary)" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false} width={62}
                tickFormatter={v => `₹${v >= 1000 ? (v/1000).toFixed(0)+"k" : v}`} />
              <Tooltip content={<ChartTooltip />} />
              <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              <Area dataKey="Income"   name="Income"   stroke="var(--positive)" fill="url(#gAnalyticsInc)" strokeWidth={2.5} dot={false} />
              <Area dataKey="Expenses" name="Expenses" stroke="var(--negative)" fill="url(#gAnalyticsExp)" strokeWidth={2.5} dot={false} />
              <Line dataKey="Net"      name="Net"      stroke="var(--info)" strokeWidth={2} dot={false} strokeDasharray="5 3" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Month-over-Month Comparison */}
      {momRows.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Month-over-Month Comparison</div>
              <div className="chart-subtitle">Spending change vs previous month</div>
            </div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Month", "Income", "ΔIncome", "Expenses", "ΔSpend", "Net"].map(h => (
                    <th key={h} style={{ padding: "10px 16px", textAlign: h === "Month" ? "left" : "right", color: "var(--text-muted)", fontWeight: 600, fontSize: 11, textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {momRows.map((row, i) => (
                  <tr key={row.month} style={{ borderBottom: "1px solid var(--border)", background: i % 2 === 0 ? "transparent" : "var(--surface-secondary)" }}>
                    <td style={{ padding: "12px 16px", fontWeight: 700, color: "var(--text-primary)" }}>{row.month}</td>
                    <td style={{ padding: "12px 16px", textAlign: "right", color: "var(--positive)", fontWeight: 600 }}>{money(row.currInc)}</td>
                    <td style={{ padding: "12px 16px", textAlign: "right" }}>
                      <span style={{ color: row.incDelta >= 0 ? "var(--positive)" : "var(--negative)", fontWeight: 700, fontSize: 12 }}>
                        {row.incDelta >= 0 ? "↑" : "↓"}{Math.abs(row.incDelta).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", color: "var(--negative)", fontWeight: 600 }}>{money(row.currExp)}</td>
                    <td style={{ padding: "12px 16px", textAlign: "right" }}>
                      <span style={{
                        color: row.delta <= 0 ? "var(--positive)" : "var(--negative)",
                        background: row.delta <= 0 ? "var(--positive-soft)" : "var(--negative-soft)",
                        padding: "2px 8px", borderRadius: 8, fontWeight: 700, fontSize: 12,
                      }}>
                        {row.delta >= 0 ? "↑" : "↓"}{Math.abs(row.delta).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: 700, color: row.currInc - row.currExp >= 0 ? "var(--positive)" : "var(--negative)" }}>
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
              <div className="chart-title">Category Intensity Map</div>
              <div className="chart-subtitle">Relative spending intensity per category</div>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
            {heatmapData.map((item) => {
              const maxVal  = heatmapData[0]?.value || 1;
              const opacity = 0.15 + (item.value / maxVal) * 0.85;
              return (
                <div key={item.category} style={{
                  padding: "16px 14px", borderRadius: 14,
                  background: `${item.color}${Math.round(opacity * 255).toString(16).padStart(2, "0")}`,
                  border: `1px solid ${item.color}40`,
                  textAlign: "center",
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: item.color, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
                    {item.category}
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 800, color: "var(--text-primary)" }}>
                    {money(item.value)}
                  </div>
                  <div style={{ marginTop: 8, height: 4, borderRadius: 4, background: "rgba(0,0,0,0.08)", overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 4,
                      width: `${(item.value / maxVal) * 100}%`,
                      background: item.color,
                      transition: "width 0.6s ease",
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
              <div className="chart-title">Forecast vs Actual</div>
              <div className="chart-subtitle">EWMA projection — 30 and 90-day outlook per category</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={forecastBars} barGap={3} barCategoryGap="25%">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-secondary)" vertical={false} />
              <XAxis dataKey="cat" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false} width={64}
                tickFormatter={v => `₹${v >= 1000 ? (v/1000).toFixed(0)+"k" : v}`} />
              <Tooltip content={<ChartTooltip />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Current"     fill="var(--text-muted)" radius={[4,4,0,0]} />
              <Bar dataKey="30-Day Proj" fill="var(--info)" radius={[4,4,0,0]} />
              <Bar dataKey="90-Day Proj" fill="#C084FC" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
          {/* Trend indicators */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            {forecastBars.map(r => (
              <div key={r.cat} style={{
                fontSize: 11, padding: "4px 10px", borderRadius: 20, fontWeight: 600,
                background: r.trend === "up" ? "var(--negative-soft)" : r.trend === "down" ? "var(--positive-soft)" : "var(--surface-secondary)",
                color: r.trend === "up" ? "var(--negative)" : r.trend === "down" ? "var(--positive)" : "var(--text-secondary)",
                border: `1px solid ${r.trend === "up" ? "rgba(255,45,45,0.4)" : r.trend === "down" ? "rgba(168,255,47,0.3)" : "var(--border)"}`,
              }}>
                {r.cat}: {r.trend === "up" ? "📈 Rising" : r.trend === "down" ? "📉 Falling" : "→ Stable"}
                {" "}({Math.round(r.confidence * 100)}% confidence)
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
              <div className="chart-title">Anomaly Timeline</div>
              <div className="chart-subtitle">{anomalies.length} unusual transactions detected</div>
            </div>
            <AlertTriangle size={18} style={{ color: "var(--warning)" }} />
          </div>

          {anomalyTimeline.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <ResponsiveContainer width="100%" height={80}>
                <BarChart data={anomalyTimeline}>
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(v) => [`${v} anomal${v !== 1 ? "ies" : "y"}`, "Count"]}
                    contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}
                  />
                  <Bar dataKey="count" fill="var(--warning)" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {anomalies.slice(0, 10).map((a) => (
              <div key={a.transaction_id} style={{
                display: "flex", alignItems: "center", gap: 12, padding: "12px 14px",
                borderRadius: 12, border: "1px solid var(--border)",
                borderLeft: `4px solid ${SEVERITY_COLOR[a.severity] || "var(--text-secondary)"}`,
                background: "var(--surface)",
              }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                  background: a.severity === "high" ? "var(--negative-soft)" : a.severity === "medium" ? "rgba(250,204,21,0.12)" : "rgba(56,189,248,0.12)",
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14,
                }}>
                  {a.severity === "high" ? "🔴" : a.severity === "medium" ? "🟡" : "🔵"}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{a.message}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                    {a.category} · {money(a.amount)} · {a.date}
                    {a.expected_range && ` · Normal: ${money(a.expected_range.min)}–${money(a.expected_range.max)}`}
                  </div>
                </div>
                <span style={{
                  fontSize: 10, padding: "2px 8px", borderRadius: 8, fontWeight: 800,
                  textTransform: "uppercase",
                  color: SEVERITY_COLOR[a.severity], background: `${SEVERITY_COLOR[a.severity]}18`,
                }}>
                  {a.severity}
                </span>
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
              <div className="chart-title">Category Breakdown</div>
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
              <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-secondary)" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false}
                tickFormatter={v => `₹${v >= 1000 ? (v/1000).toFixed(0)+"k" : v}`} />
              <YAxis type="category" dataKey="cat" tick={{ fontSize: 12, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} width={90} />
              <Tooltip
                formatter={v => [money(v), "Spend"]}
                contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}
              />
              <Bar dataKey="value" radius={[0,6,6,0]}>
                {Object.entries(byCategory)
                  .sort((a,b) => Number(b[1]) - Number(a[1]))
                  .slice(0,10)
                  .map(([cat], i) => {
                    const norm = cat.charAt(0).toUpperCase() + cat.slice(1).toLowerCase();
                    const color = CATEGORY_COLORS[norm] || CATEGORY_COLORS[cat] || paletteColor(cat, i);
                    return <Cell key={cat} fill={color} />;
                  })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
