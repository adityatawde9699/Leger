import React from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, money, CATEGORY_COLORS, paletteColor, KEYS } from "../lib";
import { CardSkeleton, QueryGate } from "../components/ui";
import ProactiveInsights from "../components/ProactiveInsights";
import {
  TrendingUp, TrendingDown, DollarSign, PiggyBank, Calendar, AlertCircle,
  BarChart3, Target, Banknote, AlertTriangle, Zap, ShoppingBag, ArrowUpRight,
} from "lucide-react";
import {
  BarChart, Bar, Area, AreaChart, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend,
  LineChart, Line, ReferenceLine,
} from "recharts";

const TIME_FILTERS = [
  { id: "30d",          label: "30 Days" },
  { id: "3m",          label: "3 Months" },
  { id: "current_year",label: "This Year" },
  { id: "all",         label: "All Time" },
];

const SEVERITY_COLOR = { high: "var(--accent)", medium: "var(--warning)", low: "var(--info)" };
const SEVERITY_BG    = { high: "rgba(255, 59, 59, 0.1)", medium: "rgba(250, 204, 21, 0.1)", low: "rgba(56, 189, 248, 0.1)" };

export default function Dashboard({ analyticsOnly = false }) {
  const [timeRange, setTimeRange] = React.useState("30d");
  const [showAllAnomalies, setShowAllAnomalies] = React.useState(false);
  const [dismissedAnomalies, setDismissedAnomalies] = React.useState(() => {
    try { return JSON.parse(localStorage.getItem("dismissed_anomalies") || "[]"); }
    catch { return []; }
  });

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

  const dismissAnomaly = (txId) => {
    const next = [...dismissedAnomalies, txId];
    setDismissedAnomalies(next);
    localStorage.setItem("dismissed_anomalies", JSON.stringify(next));
  };

  const skeleton = (
    <div className="view-dashboard">
      <div className="page-title-block">
        <h1 className="page-title">{analyticsOnly ? "Analytics" : "Dashboard"}</h1>
        <p className="page-subtitle">Loading your financial data…</p>
      </div>
      <div className="account-grid">
        {Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)}
      </div>
      <div className="charts-grid">
        <CardSkeleton /><CardSkeleton />
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

  const income       = Number(summary?.income   || 0);
  const expenses     = Number(summary?.expenses || 0);
  const net          = Number(summary?.net      || 0);
  const saved        = Math.max(0, income - expenses);
  const savingsRate  = income > 0 ? Math.round((saved / income) * 100) : 0;
  const periodLabel  = summary?.period_start && summary?.period_end
    ? `${summary.period_start} → ${summary.period_end}`
    : "All available transactions";

  const closingBalance = summary?.closing_balance != null ? Number(summary.closing_balance) : null;
  const openingBalance = summary?.opening_balance != null ? Number(summary.opening_balance) : null;
  const hasBalanceData = closingBalance !== null;

  const byCategory  = summary?.by_category || {};
  const pieRows     = Object.entries(byCategory)
    .map(([name, value]) => ({ name, value: Number(value) }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value);
  const topCat = pieRows[0]?.name || "—";

  const dayRows = Object.entries(summary?.by_day || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([d, row]) => ({
      date:     d.slice(5),
      Income:   Number(row.income),
      Expenses: Number(row.expenses),
    }));

  const monthRows = Object.entries(summary?.by_month || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, row]) => ({
      month,
      Income:   Number(row.income),
      Expenses: Number(row.expenses),
      Net:      Number(row.income) - Number(row.expenses),
    }));

  const cashIncome   = Number(summary?.cash_income   || 0);
  const cashExpenses = Number(summary?.cash_expenses || 0);
  const cashNet      = Number(summary?.cash_net      || 0);
  const hasCash = cashIncome > 0 || cashExpenses > 0;

  const topMerchants = summary?.top_merchants || [];

  // Forecast chart data
  const forecastBars = forecast?.by_category
    ? Object.entries(forecast.by_category)
        .map(([cat, proj]) => ({
          cat,
          projected: Math.round(proj.projected_30d),
          actual:    Math.round(byCategory[cat] || 0),
          trend:     proj.trend,
        }))
        .filter((r) => r.projected > 0 || r.actual > 0)
        .sort((a, b) => b.projected - a.projected)
        .slice(0, 6)
    : [];

  const visibleAnomalies = anomalies
    .filter((a) => !dismissedAnomalies.includes(a.transaction_id))
    .slice(0, showAllAnomalies ? 20 : 3);
  const hiddenCount = Math.max(0,
    anomalies.filter((a) => !dismissedAnomalies.includes(a.transaction_id)).length - 3
  );

  const kpiCards = [
    { label: "Total Income",   val: income,   change: periodLabel,   type: "positive", Icon: TrendingUp },
    { label: "Total Expenses", val: expenses, change: periodLabel,   type: "negative", Icon: TrendingDown },
    { label: "Net Savings",    val: saved,    change: income > 0 ? `${savingsRate}% savings rate` : "—", type: "positive", Icon: PiggyBank },
    { label: "Recurring",      val: summary?.recurring?.length || 0, change: "Payments detected", type: "muted", Icon: Calendar, isCount: true },
    ...(hasCash ? [{ label: "Cash Net", val: cashNet, change: "Physical cash", type: cashNet >= 0 ? "positive" : "negative", Icon: Banknote, isCash: true }] : []),
  ];

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "12px 16px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8 }}>{label}</div>
          {payload.map(p => (
            <div key={p.dataKey} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, fontWeight: 600, color: p.color, marginBottom: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: p.color }} />
              {p.dataKey}: {money(p.value)}
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  const kpiColors   = { positive: "var(--primary)", negative: "var(--accent)", muted: "var(--text-secondary)" };
  const kpiBgColors = { positive: "var(--positive-soft)", negative: "var(--negative-soft)", muted: "var(--surface-secondary)" };

  // Savings rate donut data
  const savingsDonut = [
    { name: "Saved",  value: saved },
    { name: "Spent",  value: expenses },
  ];

  return (
    <div className="view-dashboard">
      {/* Page header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 16, marginBottom: 32 }}>
        <div>
          <h1 className="page-title" style={{ marginBottom: 6 }}>
            {analyticsOnly ? "Financial Analytics" : "Financial Dashboard"}
          </h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>{periodLabel}</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {TIME_FILTERS.map(r => (
            <button
              key={r.id}
              onClick={() => setTimeRange(r.id)}
              className={timeRange === r.id ? "btn-primary" : "btn-secondary"}
              style={{ padding: "8px 16px", fontSize: 13 }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Anomaly Alert Banner ─────────────────────────────────────────── */}
      {visibleAnomalies.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <AlertTriangle size={18} style={{ color: "var(--accent)" }} />
            <span style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>
              {anomalies.filter(a => !dismissedAnomalies.includes(a.transaction_id)).length} Anomalies Detected
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)", background: "var(--surface-secondary)", padding: "2px 10px", borderRadius: 20 }}>
              Review unusual activity
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {visibleAnomalies.map((a) => (
              <div key={a.transaction_id}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
                  background: SEVERITY_BG[a.severity] || "var(--surface-secondary)",
                  border: `1px solid ${SEVERITY_COLOR[a.severity] || "var(--border)"}`,
                  borderLeft: `4px solid ${SEVERITY_COLOR[a.severity] || "var(--text-secondary)"}`,
                  borderRadius: 12,
                }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                    {a.message}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {a.category} · {money(a.amount)} · {a.date}
                  </div>
                </div>
                <span style={{
                  padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                  color: SEVERITY_COLOR[a.severity], background: SEVERITY_BG[a.severity],
                  border: `1px solid ${SEVERITY_COLOR[a.severity]}`, textTransform: "uppercase",
                }}>
                  {a.severity}
                </span>
                <button onClick={() => dismissAnomaly(a.transaction_id)}
                  style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18, lineHeight: 1, padding: "0 4px" }}>
                  ×
                </button>
              </div>
            ))}
            {hiddenCount > 0 && !showAllAnomalies && (
              <button onClick={() => setShowAllAnomalies(true)}
                style={{ background: "none", border: "1px dashed var(--border)", borderRadius: 10, padding: "8px", fontSize: 13, color: "var(--text-muted)", cursor: "pointer" }}>
                + {hiddenCount} more anomalies
              </button>
            )}
          </div>
        </div>
      )}

      {/* Hero card */}
      {!analyticsOnly && (
        <div className="card hero-card" style={{ marginBottom: 24 }}>
          <div className="hero-label">
            <DollarSign size={16} />
            {hasBalanceData ? "Closing Balance" : "Net Cash Flow"}
          </div>
          <div className="hero-amount">{money(hasBalanceData ? closingBalance : net)}</div>
          <div className={`hero-change ${net >= 0 ? "positive" : "negative"}`}>
            {net >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
            {hasBalanceData && openingBalance !== null
              ? `Opened at ${money(openingBalance)} · Net ${net >= 0 ? "+" : ""}${money(net)}`
              : income > 0 ? `${savingsRate}% savings rate` : "No income recorded yet"}
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="account-grid" style={{ marginBottom: 24 }}>
        {kpiCards.map(({ label, val, change, type, Icon, isCount, isCash }) => (
          <div className="card account-card" key={label}
            style={{ borderTop: `3px solid ${isCash ? "var(--warning)" : kpiColors[type]}` }}>
            <div className="account-card-header">
              <span className="account-label">{label}</span>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: isCash ? "rgba(250,204,21,0.16)" : kpiBgColors[type], display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon size={18} style={{ color: isCash ? "var(--warning)" : kpiColors[type] }} />
              </div>
            </div>
            <div className="account-amount">{isCount ? val : money(val)}</div>
            <div className={`account-change ${type}`} style={{ fontSize: 12 }}>
              {isCash ? <span style={{ color: "var(--info)", fontWeight: 600 }}>✦ Not in bank · Physical</span> : change}
            </div>
          </div>
        ))}
      </div>

      {/* Charts Row 1: Donut + Bar */}
      <div className="charts-grid" style={{ marginBottom: 24 }}>
        {/* Savings-Rate Donut */}
        <div className="card">
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Spending Breakdown</div>
              <div className="chart-subtitle">By category · {savingsRate}% saved</div>
            </div>
          </div>
          {pieRows.length === 0 ? (
            <div style={{ textAlign: "center", padding: "48px 0", color: "var(--text-muted)", fontSize: 14 }}>No expense data</div>
          ) : (
            <div style={{ position: "relative" }}>
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={pieRows} dataKey="value" innerRadius={62} outerRadius={95} paddingAngle={3} strokeWidth={0}>
                    {pieRows.map((r, i) => {
                      const norm = r.name.charAt(0).toUpperCase() + r.name.slice(1).toLowerCase();
                      const color = CATEGORY_COLORS[norm] || CATEGORY_COLORS[r.name] || paletteColor(r.name, i);
                      return <Cell key={r.name} fill={color} />;
                    })}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              {/* Center label */}
              <div style={{
                position: "absolute", top: "42%", left: "50%", transform: "translate(-50%,-50%)",
                textAlign: "center", pointerEvents: "none",
              }}>
                <div style={{ fontSize: 22, fontWeight: 800, color: "var(--text-primary)", lineHeight: 1 }}>
                  {savingsRate}%
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, marginTop: 2 }}>
                  saved
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Income vs Expenses bar */}
        <div className="card">
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Income vs Expenses</div>
              <div className="chart-subtitle">Last {dayRows.length} days</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={dayRows} barGap={4} barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} width={60} tickFormatter={v => `₹${v >= 1000 ? (v/1000).toFixed(0) + "k" : v}`} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="Income"   fill="var(--primary)" radius={[6, 6, 0, 0]} />
              <Bar dataKey="Expenses" fill="var(--negative)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Monthly area chart */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="chart-card-header">
          <div>
            <div className="chart-title">Monthly Cash Flow</div>
            <div className="chart-subtitle">Income and expenses across {summary?.months_covered || 0} month(s)</div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={monthRows.length > 1 ? monthRows : dayRows}>
            <defs>
              <linearGradient id="gInc" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="var(--primary)" stopOpacity={0.15} />
                <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="var(--negative)" stopOpacity={0.12} />
                <stop offset="95%" stopColor="var(--negative)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gNet" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="var(--info)" stopOpacity={0.1} />
                <stop offset="95%" stopColor="var(--info)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey={monthRows.length > 1 ? "month" : "date"} tick={{ fontSize: 11, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} width={60} tickFormatter={v => `₹${v >= 1000 ? (v/1000).toFixed(0) + "k" : v}`} />
            <Tooltip content={<CustomTooltip />} />
            <Area dataKey="Income"   stroke="var(--primary)" fill="url(#gInc)" strokeWidth={2.5} dot={false} />
            <Area dataKey="Expenses" stroke="var(--negative)" fill="url(#gExp)" strokeWidth={2.5} dot={false} />
            {monthRows.length > 0 && <Area dataKey="Net" stroke="var(--info)" fill="url(#gNet)" strokeWidth={2} dot={false} strokeDasharray="4 2" />}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Forecast vs Actual */}
      {forecastBars.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header">
            <div>
              <div className="chart-title">30-Day Spending Forecast</div>
              <div className="chart-subtitle">Projected vs current · EWMA model</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)" }}>
              <div style={{ width: 12, height: 3, background: "var(--primary)", borderRadius: 2 }} /> Projected
              <div style={{ width: 12, height: 3, background: "var(--surface-secondary)", borderRadius: 2 }} /> Current
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={forecastBars} barGap={4} barCategoryGap="28%">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="cat" tick={{ fontSize: 11, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "var(--text-secondary)", fontWeight: 500 }} axisLine={false} tickLine={false} width={62} tickFormatter={v => `₹${v >= 1000 ? (v/1000).toFixed(0) + "k" : v}`} />
              <Tooltip
                formatter={(val, name) => [money(val), name === "projected" ? "30-Day Forecast" : "Current"]}
                contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}
              />
              <Bar dataKey="actual"    fill="var(--surface-secondary)" radius={[4, 4, 0, 0]} name="Current" />
              <Bar dataKey="projected" fill="var(--primary)" radius={[4, 4, 0, 0]} name="Projected"
                label={false}
              />
            </BarChart>
          </ResponsiveContainer>
          {forecast?.budget_warnings?.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
              {forecast.budget_warnings.map((w) => (
                <div key={w.category} style={{
                  fontSize: 12, padding: "5px 12px", borderRadius: 20,
                  background: w.severity === "high" ? "var(--negative-soft)" : "rgba(250,204,21,0.12)",
                  color: w.severity === "high" ? "var(--accent)" : "var(--warning)",
                  border: `1px solid ${w.severity === "high" ? "rgba(255,45,45,0.4)" : "rgba(250,204,21,0.4)"}`,
                  fontWeight: 600,
                }}>
                  ⚠ {w.category}: projected to overspend by {money(w.projected_excess)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Top Merchants */}
      {topMerchants.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="chart-card-header" style={{ marginBottom: 16 }}>
            <div>
              <div className="chart-title">Top Merchants</div>
              <div className="chart-subtitle">Highest spend this period</div>
            </div>
            <ShoppingBag size={18} style={{ color: "var(--text-muted)" }} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {topMerchants.map((m, i) => {
              const maxAmt = topMerchants[0]?.amount || 1;
              const pct    = Math.round((m.amount / maxAmt) * 100);
              return (
                <div key={m.merchant} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: 8, background: "var(--surface-secondary)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, fontWeight: 700, color: "var(--text-muted)",
                  }}>
                    {i + 1}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                        {m.merchant.length > 35 ? m.merchant.slice(0, 35) + "…" : m.merchant}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
                        {money(m.amount)}
                      </span>
                    </div>
                    <div style={{ height: 4, borderRadius: 4, background: "var(--surface-secondary)", overflow: "hidden" }}>
                      <div style={{
                        height: "100%", width: `${pct}%`, borderRadius: 4,
                        background: `linear-gradient(90deg, var(--primary), var(--info))`,
                        transition: "width 0.6s ease",
                      }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Insights */}
      {!analyticsOnly && <ProactiveInsights />}

      {/* Rule-based insights */}
      {(summary?.insights || []).length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="chart-title" style={{ marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
            <AlertCircle size={18} style={{ color: "var(--primary)" }} /> Actionable Insights
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {summary.insights.map((item) => (
              <div key={item} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "14px 16px", background: "var(--positive-soft)", borderRadius: 12, borderLeft: "3px solid var(--primary)" }}>
                <AlertCircle size={15} style={{ color: "var(--primary)", flexShrink: 0, marginTop: 2 }} />
                <p style={{ fontSize: 14, color: "var(--text-primary)", lineHeight: 1.6, margin: 0 }}>{item}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analytics extras */}
      {analyticsOnly && (
        <div className="account-grid" style={{ marginTop: 24 }}>
          {[
            { name: "Balance / Net",  val: hasBalanceData ? money(closingBalance) : money(net), sub: hasBalanceData && openingBalance !== null ? `Opened at ${money(openingBalance)}` : savingsRate > 0 ? `+${savingsRate}% savings` : "—", Icon: DollarSign },
            { name: "Savings Rate",   val: `${savingsRate}%`, sub: "This period",                         Icon: PiggyBank },
            { name: "Total Expenses", val: money(expenses),   sub: `${pieRows.length} categories`,         Icon: BarChart3 },
            { name: "Top Category",   val: topCat,            sub: money(byCategory[topCat] || 0),         Icon: Target },
          ].map(({ name, val, sub, Icon }) => (
            <div className="card account-card" key={name}>
              <div className="account-card-header">
                <span className="account-label">{name}</span>
                <Icon size={18} style={{ color: "var(--primary)" }} />
              </div>
              <div className="account-amount" style={{ fontSize: 22 }}>{val}</div>
              <div className="account-change muted">{sub}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
