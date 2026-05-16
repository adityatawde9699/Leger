import React from "react";
import { apiFetch, money, CATEGORY_COLORS } from "../lib";
import { CardSkeleton } from "../components/ui";
import { useToast } from "../components/ui";
import ProactiveInsights from "../components/ProactiveInsights";
import {
  TrendingUp, TrendingDown, DollarSign, PiggyBank, Calendar, AlertCircle, BarChart3, Target,
} from "lucide-react";
import {
  BarChart, Bar, Area, AreaChart, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend,
} from "recharts";

export default function Dashboard({ analyticsOnly = false }) {
  const toast = useToast();
  const [summary, setSummary] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    apiFetch("/summary")
      .then(setSummary)
      .catch((e) => toast(e.message, "error"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="view-dashboard">
        <div className="page-title-block">
          <h1 className="page-title">{analyticsOnly ? "Analytics" : "Dashboard"}</h1>
        </div>
        <div className="account-grid">
          {Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
        <div className="charts-grid">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    );
  }

  const income = Number(summary?.income || 0);
  const expenses = Number(summary?.expenses || 0);
  const net = Number(summary?.net || 0);
  const saved = Math.max(0, income - expenses);
  const savingsRate = income > 0 ? Math.round((saved / income) * 100) : 0;

  const byCategory = summary?.by_category || {};
  const pieRows = Object.entries(byCategory)
    .map(([name, value]) => ({ name, value: Number(value) }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value);
  const topCat = pieRows[0]?.name || "—";

  const dayRows = Object.entries(summary?.by_day || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([d, row]) => ({
      date: d.slice(5),
      Income: Number(row.income),
      Expenses: Number(row.expenses),
    }));

  const kpiCards = [
    { label: "Total Income", val: income, change: "This period", type: "positive", Icon: TrendingUp },
    { label: "Total Expenses", val: expenses, change: "This period", type: "negative", Icon: TrendingDown },
    { label: "Money Saved", val: saved, change: income > 0 ? `${savingsRate}% of income` : "—", type: "positive", Icon: PiggyBank },
    { label: "Recurring", val: summary?.recurring?.length || 0, change: "Payments detected", type: "muted", Icon: Calendar },
  ];

  return (
    <div className="view-dashboard">
      <div className="page-title-block">
        <h1 className="page-title">{analyticsOnly ? "Financial Analytics" : "Financial Dashboard"}</h1>
        <p className="page-subtitle">{analyticsOnly ? "Detailed trends and patterns" : "Your financial picture at a glance"}</p>
      </div>

      {/* Net worth hero */}
      {!analyticsOnly && (
        <div className="card hero-card">
          <div className="hero-label"><DollarSign size={15} /> Net Balance</div>
          <div className="hero-amount">{money(net)}</div>
          <div className={`hero-change ${net >= 0 ? "positive" : "negative"}`}>
            {net >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
            {income > 0 ? `${savingsRate}% savings rate` : "No income recorded yet"}
          </div>
        </div>
      )}

      {/* KPI cards */}
      <div className="account-grid">
        {kpiCards.map(({ label, val, change, type, Icon }) => (
          <div className="card account-card" key={label}>
            <div className="account-card-header">
              <span className="account-label">{label}</span>
              <Icon size={20} className={`icon-${type}`} />
            </div>
            <div className="account-amount">
              {label === "Recurring" ? val : money(val)}
            </div>
            <div className={`account-change ${type}`}>{change}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="charts-grid">
        <div className="card">
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Spending Breakdown</div>
              <div className="chart-subtitle">By category</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={pieRows} dataKey="value" innerRadius={60} outerRadius={95} paddingAngle={3}>
                {pieRows.map((r) => (
                  <Cell key={r.name} fill={CATEGORY_COLORS[r.name] || "#94a3b8"} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => money(v)} />
              <Legend iconSize={10} iconType="circle" />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Income vs Expenses</div>
              <div className="chart-subtitle">Last {dayRows.length} days</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={dayRows} barGap={3}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
              <Tooltip formatter={(v) => money(v)} />
              <Bar dataKey="Income" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Expenses" fill="#fb7185" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Area trend */}
      <div className="card">
        <div className="chart-card-header">
          <div>
            <div className="chart-title">Cash Flow Trend</div>
            <div className="chart-subtitle">Income and expenses over time</div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={dayRows}>
            <defs>
              <linearGradient id="gInc" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#fb7185" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#fb7185" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(v) => money(v)} />
            <Area dataKey="Income" stroke="#10b981" fill="url(#gInc)" strokeWidth={2} />
            <Area dataKey="Expenses" stroke="#fb7185" fill="url(#gExp)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Proactive AI Insights */}
      {!analyticsOnly && <ProactiveInsights />}

      {/* Rule-based Insights */}
      {(summary?.insights || []).length > 0 && (
        <div className="card">
          <div className="chart-title" style={{ marginBottom: 14 }}>Actionable Insights</div>
          <div className="insights-list">
            {summary.insights.map((item) => (
              <div className="insight-item" key={item}>
                <AlertCircle size={15} className="icon-accent" />
                <p>{item}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analytics extra: top categories */}
      {analyticsOnly && (
        <div className="account-grid">
          {[
            { name: "Net Balance", val: money(net), sub: savingsRate > 0 ? `+${savingsRate}% savings` : "—", Icon: DollarSign },
            { name: "Savings Rate", val: `${savingsRate}%`, sub: "This period", Icon: PiggyBank },
            { name: "Total Expenses", val: money(expenses), sub: `${pieRows.length} categories`, Icon: BarChart3 },
            { name: "Top Category", val: topCat, sub: money(byCategory[topCat] || 0), Icon: Target },
          ].map(({ name, val, sub, Icon }) => (
            <div className="card analytics-stat-card" key={name}>
              <div className="analytics-stat-card-top">
                <div className="analytics-stat-name">{name}</div>
                <Icon size={18} className="analytics-stat-icon" />
              </div>
              <div className="analytics-stat-value">{val}</div>
              <div className="analytics-stat-sub">{sub}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
