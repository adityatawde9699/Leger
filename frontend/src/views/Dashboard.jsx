import React from "react";
import { apiFetch, compactMoney, money, today, formatDay, formatMonth, formatRange } from "../lib";
import { CardSkeleton } from "../components/ui";
import { useToast } from "../components/ui";
import ProactiveInsights from "../components/ProactiveInsights";
import FirstRunSetup from "../components/FirstRunSetup";
import CurrencyMismatchNotice from "../components/CurrencyMismatchNotice";
import DailyPositionOverview from "../components/DailyPositionOverview";
import { Eye, EyeOff, RefreshCw, X, Info } from "lucide-react";
import {
  BarChart, Bar, Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid,
} from "recharts";

const TIME_FILTERS = [
  { id: "this_month",   label: "This month" },
  { id: "30d",          label: "30 days" },
  { id: "3m",           label: "3 months" },
  { id: "current_year", label: "This year" },
  { id: "all",          label: "All time" },
];

const SEVERITY_LABEL = { high: "High", medium: "Medium", low: "Low" };

// Chart ink: one accent per chart, everything else in neutral steps.
const INK = {
  accent: "#b6e35a",
  neutral: "#5c5c62",
  neutralLight: "#85858b",
  grid: "rgba(237,237,237,0.06)",
  axis: { fontSize: 11, fill: "#85858b", fontFamily: "IBM Plex Mono, monospace" },
};

export default function Dashboard({ analyticsOnly, onNavigate, onAddTransaction }) {
  const toast = useToast();
  const [summary,   setSummary]   = React.useState(null);
  const [historySummary, setHistorySummary] = React.useState(null);
  const [loading,   setLoading]   = React.useState(true);
  const [timeRange, setTimeRange] = React.useState("this_month");
  const [showQuality, setShowQuality] = React.useState(false);
  const [anomalies, setAnomalies] = React.useState([]);
  const [forecast,  setForecast]  = React.useState(null);
  const [goals, setGoals] = React.useState([]);
  const [budgets, setBudgets] = React.useState(null);
  const [profileSettings, setProfileSettings] = React.useState(null);
  const [accounts, setAccounts] = React.useState([]);
  const [importJobs, setImportJobs] = React.useState([]);
  const [recurringRules, setRecurringRules] = React.useState([]);
  const [dailyPosition, setDailyPosition] = React.useState(null);
  const [comparison, setComparison] = React.useState(null);
  const [loadError, setLoadError] = React.useState("");
  const [confirmingRecurring, setConfirmingRecurring] = React.useState(null);
  const [retryingImport, setRetryingImport] = React.useState(null);
  const [cancellingImport, setCancellingImport] = React.useState(null);
  const [showAllAnomalies, setShowAllAnomalies] = React.useState(false);
  const [dismissedAnomalies, setDismissedAnomalies] = React.useState(() => {
    try { return JSON.parse(localStorage.getItem("dismissed_anomalies") || "[]"); }
    catch { return []; }
  });
  const [insightFeedback, setInsightFeedback] = React.useState({});
  const [showClosingBalance, setShowClosingBalance] = React.useState(true);
  const [cashFlowView, setCashFlowView] = React.useState("months");

  React.useEffect(() => {
    setLoading(true);
    setLoadError("");
    Promise.all([
      apiFetch(`/summary?range=${timeRange}`),
      apiFetch("/summary?range=all").catch(() => null),
      apiFetch(`/analytics/anomalies?range=${timeRange}`).catch(() => []),
      apiFetch(`/analytics/forecast`).catch(() => null),
      apiFetch("/goals").catch(() => []),
      apiFetch("/imports/jobs?limit=10").catch(() => []),
      apiFetch("/recurring").catch(() => []),
      apiFetch("/budgets").catch(() => null),
      apiFetch("/profile").catch(() => null),
      apiFetch("/accounts").catch(() => []),
      apiFetch(`/daily-position?as_of=${today()}`).catch((error) => ({ error: error.message })),
      apiFetch(`/analytics/compare?days=30&end=${today()}`).catch(() => ({ status: "error" })),
    ]).then(([s, all, a, f, g, jobs, rules, b, profile, userAccounts, position, periodComparison]) => {
      setSummary(s);
      setHistorySummary(all);
      setAnomalies(Array.isArray(a) ? a : (a?.items || []));
      setForecast(f);
      setGoals(Array.isArray(g) ? g : []);
      setImportJobs(Array.isArray(jobs) ? jobs : []);
      setRecurringRules(Array.isArray(rules) ? rules : []);
      setBudgets(Array.isArray(b) ? b : null);
      setProfileSettings(profile);
      setAccounts(Array.isArray(userAccounts) ? userAccounts : []);
      setDailyPosition(position);
      setComparison(periodComparison);
    }).catch((e) => { setLoadError(e.message); toast(e.message, "error"); })
      .finally(() => setLoading(false));
  }, [timeRange]);

  React.useEffect(() => {
    if (!importJobs.some((job) => ["pending", "processing"].includes(job.status))) return undefined;
    const timer = setInterval(() => {
      apiFetch("/imports/jobs?limit=10").then((jobs) => {
        if (Array.isArray(jobs)) setImportJobs(jobs);
      }).catch(() => {});
    }, 3000);
    return () => clearInterval(timer);
  }, [importJobs]);

  const dismissAnomaly = (txId) => {
    const next = [...dismissedAnomalies, txId];
    setDismissedAnomalies(next);
    localStorage.setItem("dismissed_anomalies", JSON.stringify(next));
  };

  const sendInsightFeedback = async (insight, value) => {
    if (!insight?.id || insightFeedback[insight.id]) return;
    setInsightFeedback((current) => ({ ...current, [insight.id]: value }));
    try {
      await apiFetch("/insights/feedback", {
        method: "POST",
        body: JSON.stringify({ insight_id: insight.id, feedback: value }),
      });
    } catch {
      // Feedback is optional and must not interrupt financial workflows.
    }
  };

  const openInsightAction = (insight) => {
    if (insight.action_type === "open_goals") onNavigate?.("goals");
    else if (insight.action_type === "view_analytics") onNavigate?.("analytics");
    else onNavigate?.("transactions");
  };

  const retryImport = async (jobId) => {
    setRetryingImport(jobId);
    try {
      const updated = await apiFetch(`/imports/jobs/${jobId}/retry`, { method: "POST" });
      setImportJobs((jobs) => jobs.map((job) => job.id === jobId ? updated : job));
      toast("Import retry started", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setRetryingImport(null);
    }
  };

  const cancelImport = async (jobId) => {
    setCancellingImport(jobId);
    try {
      const updated = await apiFetch(`/imports/jobs/${jobId}/cancel`, { method: "POST" });
      setImportJobs((jobs) => jobs.map((job) => job.id === jobId ? updated : job));
      toast("Import cancellation requested", "info");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setCancellingImport(null);
    }
  };

  const confirmRecurring = async (payment) => {
    setConfirmingRecurring(payment.description);
    try {
      const rule = await apiFetch("/recurring", { method: "POST", body: JSON.stringify({
        description: payment.description,
        category: payment.category,
        cadence: payment.cadence,
        average_amount: payment.average_amount,
        minimum_amount: payment.minimum_amount,
        maximum_amount: payment.maximum_amount,
        next_expected: payment.next_expected,
        confidence: payment.confidence,
        status: "active",
        confirmed: true,
        evidence_transaction_ids: (payment.evidence || []).map((item) => item.transaction_id),
      }) });
      setRecurringRules((rules) => [...rules, rule]);
      toast("Recurring payment confirmed", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setConfirmingRecurring(null); }
  };

  if (loading) {
    return (
      <div className="view-dashboard">
        <div className="page-title-block">
          <h1 className="page-title">{analyticsOnly ? "Analytics" : "Dashboard"}</h1>
          <p className="page-subtitle">Loading your ledger</p>
        </div>
        <div className="account-grid">
          {Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
        <div className="charts-grid">
          <CardSkeleton /><CardSkeleton />
        </div>
      </div>
    );
  }

  if (loadError || !summary) {
    return <div className="view-dashboard"><h1 className="page-title" style={{ marginBottom: 24 }}>Dashboard</h1><div className="notice negative" role="alert">
      <Info aria-hidden="true" /><span><strong>Your ledger could not load.</strong> {loadError || "Refresh to try again."} Do not rely on earlier numbers until it reloads.</span>
    </div></div>;
  }

  if (summary?.data_quality?.currency_mismatch_count > 0) {
    return <CurrencyMismatchNotice title={analyticsOnly ? "Analytics" : "Your money overview"} onNavigate={onNavigate} />;
  }

  const income       = Number(summary?.income   || 0);
  const expenses     = Number(summary?.expenses || 0);
  const net          = Number(summary?.net      || 0);
  const saved        = Math.max(0, income - expenses);
  const savingsRate  = income > 0 ? Math.round((saved / income) * 100) : 0;
  const periodLabel  = summary?.period_start && summary?.period_end
    ? formatRange(summary.period_start, summary.period_end)
    : "All recorded transactions";
  const allQuality = historySummary?.data_quality || {};
  const isFirstRun = !analyticsOnly
    && allQuality.transaction_count === 0
    && allQuality.pending_transactions === 0
    && allQuality.excluded_transactions === 0;
  const needsSetup = isFirstRun && profileSettings && !profileSettings.onboarding_completed;
  const nextAction = isFirstRun
    ? { title: "Add your first transactions", reason: "Start with a few entries or import a statement to get a useful spending picture.", label: "Add or import", run: onAddTransaction }
    : allQuality.failed_imports > 0
      ? { title: "Review a failed statement import", reason: `${allQuality.failed_imports} statement import${allQuality.failed_imports === 1 ? " needs" : "s need"} attention before all rows are in your ledger.`, label: "Open import & entry", run: onAddTransaction }
      : allQuality.pending_transactions > 0
        ? { title: "Review pending transactions", reason: `${allQuality.pending_transactions} entries are excluded from committed totals until you review them.`, label: "Review pending", run: () => onNavigate?.("transactions", { filter: "Pending" }) }
      : allQuality.uncategorized_count > 0
        ? { title: "Improve your categories", reason: `${allQuality.uncategorized_count} entries are uncategorized or marked Other, which makes category comparisons less useful.`, label: "Review uncategorized", run: () => onNavigate?.("transactions", { filter: "Needs review" }) }
        : allQuality.unassigned_account_count > 0
          ? { title: "Assign transactions to accounts", reason: `${allQuality.unassigned_account_count} non-cash entries are not linked to an account, so account balances may be incomplete.`, label: "Review accounts", run: () => onNavigate?.("accounts") }
      : allQuality.stale_account_count > 0
        ? { title: "Reconcile an account balance", reason: `${allQuality.stale_account_count} active account${allQuality.stale_account_count === 1 ? " has" : "s have"} no recent reconciliation.`, label: "Review accounts", run: () => onNavigate?.("accounts") }
        : budgets?.length === 0
          ? { title: "Set one spending target", reason: "A budget gives you a personal reference point for the next month. You can start with a suggested amount based on your history.", label: "Set a budget", run: () => onNavigate?.("budgets") }
          : !goals.some((goal) => goal.status === "active")
            ? { title: "Choose a financial goal", reason: "A goal turns your monthly picture into a concrete plan you can track.", label: "Create a goal", run: () => onNavigate?.("goals") }
            : null;

  const closingBalance = summary?.closing_balance != null ? Number(summary.closing_balance) : null;
  const openingBalance = summary?.opening_balance != null ? Number(summary.opening_balance) : null;
  const hasBalanceData = closingBalance !== null;
  const nextGoal = goals.find((goal) => goal.status === "active");
  const nextGoalProgress = nextGoal && Number(nextGoal.target_amount) > 0
    ? Math.min(100, Math.max(0, Number(nextGoal.current_amount) / Number(nextGoal.target_amount) * 100))
    : 0;

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
      date:     formatDay(d),
      Income:   Number(row.income),
      Expenses: Number(row.expenses),
    }));

  const monthRows = Object.entries(summary?.by_month || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, row]) => ({
      month:    formatMonth(month, { year: false }),
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

  const figures = [
    { label: "Income",    val: money(income),   sub: `${pieRows.length ? "Recorded credits" : "No credits recorded"}` },
    { label: "Spending",  val: money(expenses), sub: pieRows.length ? `Across ${pieRows.length} categor${pieRows.length === 1 ? "y" : "ies"}` : "No spending recorded" },
    { label: "Saved",     val: money(saved),    sub: income > 0 ? `${savingsRate}% of income` : "No income recorded", accent: saved > 0 },
    { label: "Recurring", val: String(summary?.recurring?.length || 0), sub: "Payments detected" },
    ...(hasCash ? [{ label: "Cash net", val: money(cashNet), sub: "Physical cash, not in a bank", wide: true }] : []),
  ];

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ background: "var(--surface-secondary)", border: "1px solid var(--border-hover)", borderRadius: 8, padding: "8px 12px", boxShadow: "var(--shadow-float)" }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
        {payload.map((p) => (
          <div key={p.dataKey} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
            <span className="status-dot" style={{ background: p.color || p.stroke }} />
            <span style={{ flex: 1 }}>{p.name || p.dataKey}</span>
            <span className="num" style={{ color: "var(--text-primary)" }}>{money(p.value)}</span>
          </div>
        ))}
      </div>
    );
  };

  const dashboardInsightClaims = summary?.insight_claims || summary?.analysis?.insight_claims || [];
  const [flowView, setFlowView] = [cashFlowView, setCashFlowView];
  const flowRows = flowView === "days" || monthRows.length < 2 ? dayRows : monthRows;
  const flowKey  = flowView === "days" || monthRows.length < 2 ? "date" : "month";
  const categoryTotal = pieRows.reduce((sum, r) => sum + r.value, 0) || 1;
  const cardholder = profileSettings?.display_name || profileSettings?.email?.split("@")[0] || "Ledger";
  const visibleAnomalyCount = anomalies.filter((a) => !dismissedAnomalies.includes(a.transaction_id)).length;

  return (
    <div className="view-dashboard">
      <div className="dashboard-header">
        <div>
          <h1 className="page-title">{analyticsOnly ? "Analytics" : "Dashboard"}</h1>
          <p className="page-subtitle">{periodLabel}</p>
        </div>
        <div className="dashboard-header-tools">
          {nextGoal && (
            <button className="dashboard-goal" onClick={() => onNavigate?.("goals")} aria-label={`Open goal ${nextGoal.name}, ${nextGoalProgress.toFixed(0)}% complete`}>
              <span>Goal</span>
              <strong>{nextGoal.name}</strong>
              <span className="track" aria-hidden="true"><i style={{ width: `${nextGoalProgress}%` }} /></span>
              <span className="num">{nextGoalProgress.toFixed(0)}%</span>
            </button>
          )}
          <div className="segmented" role="group" aria-label="Period">
            {TIME_FILTERS.map((r) => (
              <button key={r.id} type="button" aria-pressed={timeRange === r.id} onClick={() => setTimeRange(r.id)}>{r.label}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Make analytical limits visible before showing recommendations. */}
      {summary?.data_quality?.warnings?.length > 0 && (
        <div className={`notice warning quality-notice${showQuality ? " expanded" : ""}`} style={{ marginBottom: 16 }}>
          <Info aria-hidden="true" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="notice-head">
              <strong>Analysis confidence: {summary.data_quality.coverage}</strong>
              {/* Shown on phones only: the warnings collapse to keep the figures above the fold. */}
              <button type="button" className="btn-link notice-toggle" aria-expanded={showQuality} onClick={() => setShowQuality((v) => !v)}>
                {showQuality ? "Hide" : "Details"}
              </button>
            </div>
            <div className="notice-detail">{summary.data_quality.warnings.join(" · ")}. Insights use only the data currently in Ledger.</div>
          </div>
        </div>
      )}

      {needsSetup && <FirstRunSetup
        initialProfile={profileSettings}
        accounts={accounts}
        goals={goals}
        onProfileUpdated={setProfileSettings}
        onDone={() => {
          setProfileSettings((current) => current ? { ...current, onboarding_completed: true } : current);
          Promise.all([
            apiFetch("/accounts"), apiFetch("/goals"), apiFetch("/summary?range=all"),
            apiFetch(`/daily-position?as_of=${today()}`),
          ]).then(([latestAccounts, latestGoals, latestSummary, latestPosition]) => {
            setAccounts(latestAccounts); setGoals(latestGoals); setHistorySummary(latestSummary); setDailyPosition(latestPosition);
          }).catch((error) => toast(error.message, "error"));
        }}
        onAddActivity={onAddTransaction}
      />}

      {/* Primary financial summary: the card, then the period figures beside it. */}
      <div className={analyticsOnly ? "" : "dashboard-top"}>
        {!analyticsOnly && (
          <div>
            <div className="balance-card">
              <div className="balance-card-top">
                <span className="balance-card-brand"><LedgerMark />Ledger</span>
                <button type="button" className="balance-card-eye" onClick={() => setShowClosingBalance((value) => !value)} aria-label={showClosingBalance ? "Hide balance" : "Show balance"} aria-pressed={!showClosingBalance}>
                  {showClosingBalance ? <Eye size={16} strokeWidth={1.5} /> : <EyeOff size={16} strokeWidth={1.5} />}
                </button>
              </div>
              <div className="balance-card-chip" aria-hidden="true" />
              <div className="balance-card-label">{hasBalanceData ? "Closing balance" : "Net cash flow"}</div>
              <div className="balance-card-value">{showClosingBalance ? money(hasBalanceData ? closingBalance : net) : "••••••"}</div>
              <div className="balance-card-foot">
                <div>{cardholder}</div>
                <div className="end">{hasBalanceData && openingBalance !== null ? <>Opened at <strong>{showClosingBalance ? money(openingBalance) : "••••"}</strong></> : summary?.period_end ? <>As of <strong>{formatDay(summary.period_end, { year: true })}</strong></> : null}</div>
              </div>
            </div>
            <p className="balance-card-note">{hasBalanceData ? "From one recorded statement balance, not cash across all accounts" : "Income minus spending, not a bank balance"}</p>
          </div>
        )}
        <div className="dashboard-figures" style={analyticsOnly ? { gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", marginBottom: 16 } : undefined}>
          {figures.map(({ label, val, sub, accent, wide }) => (
            <div className="card account-card" key={label} style={wide ? { gridColumn: "1 / -1" } : undefined}>
              <div className="account-card-header"><span className="account-label">{label}</span></div>
              <div className="account-amount" style={accent ? { color: "var(--primary)" } : undefined}>{val}</div>
              <div className="account-change muted">{sub}</div>
            </div>
          ))}
        </div>
      </div>

      {!analyticsOnly && <DailyPositionOverview
        position={dailyPosition}
        nextAction={needsSetup ? null : nextAction}
        onNavigate={onNavigate}
        onReviewed={async () => setDailyPosition(await apiFetch(`/daily-position?as_of=${today()}`))}
      />}

      {!analyticsOnly && comparison?.status === "ready" && comparison.current.transaction_count >= 5 && comparison.previous.transaction_count >= 5 && (
        <div className="card dashboard-callout">
          <div className="dashboard-callout-body">
            <div className="chart-title">Last 30 days vs the 30 before</div>
            <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: "20px", margin: "4px 0 0" }}>
              Spending {Number(comparison.changes.expenses) > 0 ? "rose" : Number(comparison.changes.expenses) < 0 ? "fell" : "was unchanged"} by <span className="num" style={{ color: "var(--text-primary)" }}>{money(Math.abs(Number(comparison.changes.expenses)))}</span>.
              {" "}Based on {comparison.current.transaction_count} current and {comparison.previous.transaction_count} prior posted transactions.
            </p>
          </div>
          <button className="btn-secondary" onClick={() => onNavigate?.("analytics")}>Open comparison</button>
        </div>
      )}
      {!analyticsOnly && allQuality.transaction_count > 0 && comparison?.status !== "error" && (!comparison || comparison.status !== "ready" || comparison.current.transaction_count < 5 || comparison.previous.transaction_count < 5) && (
        <div className="card dashboard-callout">
          <div className="dashboard-callout-body">
            <div className="chart-title">Not enough history to compare yet</div>
            <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: "20px", margin: "4px 0 0" }}>
              Ledger needs at least five posted transactions in each of two consecutive 30-day windows. Add or import older activity to build a comparison.
            </p>
          </div>
          <button className="btn-secondary" onClick={onAddTransaction}>Add or import activity</button>
        </div>
      )}
      {!analyticsOnly && comparison?.status === "error" && <div className="notice" role="status" style={{ marginBottom: 16 }}><Info aria-hidden="true" /><span>The period comparison could not load. Open Analytics or refresh to try again.</span></div>}

      {importJobs.some((job) => ["failed", "cancelled", "pending", "processing"].includes(job.status)) && (
        <div className="card" style={{ marginBottom: 16, padding: 20 }}>
          <div className="chart-card-header" style={{ marginBottom: 12 }}>
            <div className="chart-title" style={{ display: "flex", alignItems: "center", gap: 8 }}><RefreshCw size={16} strokeWidth={1.5} style={{ color: "var(--text-muted)" }} />Statement imports</div>
            <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Processing status</span>
          </div>
          <div className="ledger-list">
            {importJobs.filter((job) => ["failed", "cancelled", "pending", "processing"].includes(job.status)).slice(0, 5).map((job) => (
              <div key={job.id} className="ledger-row">
                <div style={{ minWidth: 0 }}>
                  <div className="name">{job.file_name}</div>
                  <div className="sub" style={{ color: job.status === "failed" ? "var(--negative)" : undefined }}>
                    {job.status === "failed" ? (job.error_message || "Import failed") : job.status === "cancelled" ? (job.error_message || "Import cancelled") : job.status === "processing" ? <>Processing <span className="num">{job.processed_rows || 0}/{job.total_rows || "…"}</span> rows</> : "Waiting to process"}
                  </div>
                </div>
                <div>
                  {(job.status === "failed" || job.status === "cancelled") && (
                    <button className="btn-secondary btn-sm" disabled={retryingImport === job.id} onClick={() => retryImport(job.id)}>
                      <RefreshCw size={12} /> {retryingImport === job.id ? "Retrying" : "Retry"}
                    </button>
                  )}
                  {["pending", "processing"].includes(job.status) && (
                    <button className="btn-secondary btn-sm" disabled={cancellingImport === job.id} onClick={() => cancelImport(job.id)}>
                      {cancellingImport === job.id ? "Cancelling" : "Cancel"}
                    </button>
                  )}
                </div>
                {job.total_rows > 0 && ["pending", "processing"].includes(job.status) && (
                  <div className="bar"><i className="lead" style={{ width: `${Math.min(100, Math.round(((job.processed_rows || 0) / job.total_rows) * 100))}%` }} /></div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {(summary?.recurring?.length > 0 || visibleAnomalies.length > 0) && (
        <div className="charts-grid" style={summary?.recurring?.length > 0 && visibleAnomalies.length > 0 ? undefined : { gridTemplateColumns: "1fr" }}>
          {summary?.recurring?.length > 0 && (
            <div className="card" style={{ padding: 20 }}>
              <div className="chart-card-header" style={{ marginBottom: 12 }}>
                <div>
                  <div className="chart-title">Likely recurring payments</div>
                  <div className="chart-subtitle">Confirm before treating them as subscriptions</div>
                </div>
              </div>
              <div className="ledger-list">
                {summary.recurring.slice(0, 4).map((payment) => {
                  const confirmed = recurringRules.some((rule) => rule.description === payment.description && rule.category === payment.category);
                  return (
                    <div key={`${payment.description}-${payment.category}`} className="ledger-row" style={{ gridTemplateColumns: "1fr auto auto" }}>
                      <div style={{ minWidth: 0 }}>
                        <div className="name">{payment.description}</div>
                        <div className="sub">{payment.cadence} · {payment.count} matches · <span className="num">{Math.round(payment.confidence * 100)}%</span> confidence</div>
                      </div>
                      <div className="amt">{money(payment.average_amount)}<span style={{ color: "var(--text-muted)" }}>/mo</span></div>
                      {confirmed ? (
                        <span className="sub" style={{ width: 72, textAlign: "right" }}>Confirmed</span>
                      ) : (
                        <button className="btn-secondary btn-sm" style={{ width: 72 }} onClick={() => confirmRecurring(payment)} disabled={confirmingRecurring === payment.description}>
                          {confirmingRecurring === payment.description ? "Saving" : "Confirm"}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {visibleAnomalies.length > 0 && (
            <div className="card" style={{ padding: 20 }}>
              <div className="chart-card-header" style={{ marginBottom: 12 }}>
                <div>
                  <div className="chart-title">Unusual activity <span className="num" style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 4 }}>{visibleAnomalyCount}</span></div>
                  <div className="chart-subtitle">Transactions far from your usual pattern</div>
                </div>
              </div>
              <div className="ledger-list">
                {visibleAnomalies.map((a) => (
                  <div key={a.transaction_id} className="ledger-row" style={{ gridTemplateColumns: "auto 1fr auto auto" }}>
                    <span className={`status-dot ${a.severity}`} aria-label={`${SEVERITY_LABEL[a.severity] || a.severity} severity`} />
                    <div style={{ minWidth: 0 }}>
                      <div className="name" style={{ whiteSpace: "normal" }}>{a.message}</div>
                      <div className="sub">{a.category} · {formatDay(a.date)} · {SEVERITY_LABEL[a.severity] || a.severity}</div>
                    </div>
                    <div className="amt">{money(a.amount)}</div>
                    <button className="toast-close" onClick={() => dismissAnomaly(a.transaction_id)} aria-label={`Dismiss: ${a.message}`}>
                      <X size={14} strokeWidth={1.5} />
                    </button>
                  </div>
                ))}
              </div>
              {hiddenCount > 0 && !showAllAnomalies && (
                <button className="btn-link" onClick={() => setShowAllAnomalies(true)} style={{ marginTop: 12, padding: 0, fontSize: 13 }}>
                  Show {hiddenCount} more
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Lead chart: cash flow, with spending by category as a ranked list beside it */}
      <div className="charts-grid lead">
        <div className="card">
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Cash flow</div>
              <div className="chart-subtitle">
                {flowRows.length === 0 ? "Nothing recorded this period" : flowKey === "month" ? `Income and spending across ${summary?.months_covered || monthRows.length} months` : `Income and spending, last ${dayRows.length} days`}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", justifyContent: "flex-end" }}>
              {flowRows.length > 0 && <div className="chart-legend" aria-hidden="true">
                <span><i style={{ background: INK.accent }} />Income</span>
                <span><i style={{ background: INK.neutralLight }} />Spending</span>
              </div>}
              {monthRows.length > 1 && (
                <div className="segmented" role="group" aria-label="Cash flow scale">
                  <button type="button" aria-pressed={flowKey === "month"} onClick={() => setFlowView("months")}>Months</button>
                  <button type="button" aria-pressed={flowKey === "date"} onClick={() => setFlowView("days")}>Days</button>
                </div>
              )}
            </div>
          </div>
          {flowRows.length === 0 ? (
            <div className="chart-empty">No income or spending in this period</div>
          ) : (
          <div className="chart-box chart-box-lead">
          <ResponsiveContainer width="100%" height="100%">
            {flowKey === "month" ? (
              <AreaChart data={flowRows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gIncome" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={INK.accent} stopOpacity={0.14} />
                    <stop offset="100%" stopColor={INK.accent} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={INK.grid} vertical={false} />
                <XAxis dataKey="month" tick={INK.axis} axisLine={false} tickLine={false} dy={8} />
                <YAxis tick={INK.axis} axisLine={false} tickLine={false} width={56} tickFormatter={compactMoney} />
                <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(237,237,237,0.12)" }} />
                <Area type="monotone" dataKey="Income" stroke={INK.accent} fill="url(#gIncome)" strokeWidth={2} dot={false} activeDot={{ r: 3, strokeWidth: 0 }} />
                <Area type="monotone" dataKey="Expenses" name="Spending" stroke={INK.neutralLight} fill="none" strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 0 }} />
              </AreaChart>
            ) : (
              <BarChart data={flowRows} barGap={2} barCategoryGap="32%" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={INK.grid} vertical={false} />
                <XAxis dataKey="date" tick={INK.axis} axisLine={false} tickLine={false} dy={8} interval="preserveStartEnd" />
                <YAxis tick={INK.axis} axisLine={false} tickLine={false} width={56} tickFormatter={compactMoney} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(237,237,237,0.04)" }} />
                <Bar dataKey="Income" fill={INK.accent} radius={[2, 2, 0, 0]} maxBarSize={14} />
                <Bar dataKey="Expenses" name="Spending" fill={INK.neutral} radius={[2, 2, 0, 0]} maxBarSize={14} />
              </BarChart>
            )}
          </ResponsiveContainer>
          </div>
          )}
        </div>

        <div className="card">
          <div className="chart-card-header">
            <div>
              <div className="chart-title">Spending by category</div>
              <div className="chart-subtitle">{pieRows.length ? <>Largest: {topCat}</> : "Nothing recorded this period"}</div>
            </div>
          </div>
          {pieRows.length === 0 ? (
            <div className="chart-empty">No spending in this period</div>
          ) : (
            <div className="ledger-list has-bars">
              {pieRows.slice(0, 7).map((r, i) => (
                <div key={r.name} className="ledger-row">
                  <span className="name">{r.name}</span>
                  <span className="amt">{money(r.value)} <span style={{ color: "var(--text-muted)", display: "inline-block", width: 36 }}>{Math.round((r.value / categoryTotal) * 100)}%</span></span>
                  <div className="bar"><i className={i === 0 ? "lead" : ""} style={{ width: `${(r.value / pieRows[0].value) * 100}%` }} /></div>
                </div>
              ))}
              {pieRows.length > 7 && <div className="sub" style={{ paddingTop: 8, fontSize: 12, color: "var(--text-muted)" }}>{pieRows.length - 7} more in Analytics</div>}
            </div>
          )}
        </div>
      </div>

      {/* Forecast and merchants: a comparison chart beside a ranked list */}
      {(forecastBars.length > 0 || topMerchants.length > 0) && (
        <div className={`charts-grid${forecastBars.length > 0 && topMerchants.length > 0 ? " lead" : ""}`} style={forecastBars.length > 0 && topMerchants.length > 0 ? undefined : { gridTemplateColumns: "1fr" }}>
          {forecastBars.length > 0 && (
            <div className="card">
              <div className="chart-card-header">
                <div>
                  <div className="chart-title">Next 30 days, by category</div>
                  <div className="chart-subtitle">Projected spending against this period so far</div>
                </div>
                <div className="chart-legend" aria-hidden="true">
                  <span><i style={{ background: INK.neutral }} />So far</span>
                  <span><i style={{ background: INK.accent }} />Projected</span>
                </div>
              </div>
              <div className="chart-box"><ResponsiveContainer width="100%" height="100%">
                <BarChart data={forecastBars} barGap={2} barCategoryGap="36%" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={INK.grid} vertical={false} />
                  <XAxis dataKey="cat" tick={{ ...INK.axis, fontFamily: "IBM Plex Sans, sans-serif", fontSize: 12 }} axisLine={false} tickLine={false} dy={8} />
                  <YAxis tick={INK.axis} axisLine={false} tickLine={false} width={56} tickFormatter={compactMoney} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(237,237,237,0.04)" }} />
                  <Bar dataKey="actual" name="So far" fill={INK.neutral} radius={[2, 2, 0, 0]} maxBarSize={20} />
                  <Bar dataKey="projected" name="Projected" fill={INK.accent} radius={[2, 2, 0, 0]} maxBarSize={20} />
                </BarChart>
              </ResponsiveContainer></div>
              {forecast?.budget_warnings?.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
                  {forecast.budget_warnings.map((w) => (
                    <div key={w.category} className={`notice ${w.severity === "high" ? "negative" : "warning"}`} style={{ padding: "8px 12px" }}>
                      <Info aria-hidden="true" />
                      <span><strong>{w.category}</strong> is on pace to go over budget by <span className="num" style={{ color: "var(--text-primary)" }}>{money(w.projected_breach)}</span>{w.historical_monthly_avg != null && <>, against a usual <span className="num">{money(w.historical_monthly_avg)}</span> a month</>}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {topMerchants.length > 0 && (
            <div className="card">
              <div className="chart-card-header">
                <div>
                  <div className="chart-title">Top merchants</div>
                  <div className="chart-subtitle">Highest spending this period</div>
                </div>
              </div>
              <div className="ledger-list has-bars">
                {topMerchants.map((m, i) => (
                  <div key={m.merchant} className="ledger-row">
                    <span className="name" title={m.merchant}>{m.merchant}</span>
                    <span className="amt">{money(m.amount)}</span>
                    <div className="bar"><i className={i === 0 ? "lead" : ""} style={{ width: `${Math.round((m.amount / (topMerchants[0]?.amount || 1)) * 100)}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* AI Insights */}
      {!analyticsOnly && <ProactiveInsights onNavigate={onNavigate} />}

      {/* Rule-based insights */}
      {(dashboardInsightClaims.length > 0 || (summary?.insights || []).length > 0) && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="chart-card-header" style={{ marginBottom: 8 }}>
            <div className="chart-title">What to look at</div>
          </div>
          <div className="ledger-list">
            {dashboardInsightClaims.length > 0 ? dashboardInsightClaims.map((item) => (
              <div key={item.id} className="ledger-row" style={{ gridTemplateColumns: "minmax(0, 1fr)", padding: "12px 0" }}>
                <div>
                  <p style={{ fontSize: 14, lineHeight: "22px", color: "var(--text-primary)", margin: 0 }}>{item.claim}</p>
                  <div className="sub" style={{ marginTop: 4 }}>
                    Based on {item.evidence?.transaction_ids?.length || 0} transaction{item.evidence?.transaction_ids?.length === 1 ? "" : "s"} · {item.evidence?.method} · {item.confidence} confidence
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 8 }}>
                    <button className="btn-secondary btn-sm insight-action-btn" type="button" onClick={() => openInsightAction(item)}>
                      {item.recommended_action || "Review evidence"}
                    </button>
                    {insightFeedback[item.id] ? (
                      <span className="sub">Marked {insightFeedback[item.id].replace("_", " ")}</span>
                    ) : (
                      <span className="insight-feedback sub">
                        <span>Useful?</span>
                        {[["helpful", "Yes"], ["inaccurate", "Not accurate"], ["too_generic", "Too generic"]].map(([value, label]) => (
                          <button key={value} type="button" className="btn-link" onClick={() => sendInsightFeedback(item, value)} style={{ fontSize: 12, padding: 0 }}>
                            {label}
                          </button>
                        ))}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )) : summary.insights.map((item) => (
              <div key={item} className="ledger-row" style={{ gridTemplateColumns: "minmax(0, 1fr)", padding: "12px 0" }}>
                <p style={{ fontSize: 14, lineHeight: "22px", color: "var(--text-primary)", margin: 0 }}>{item}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analytics extras */}
      {analyticsOnly && (
        <div className="account-grid" style={{ marginTop: 16 }}>
          {[
            { name: "Balance or net", val: hasBalanceData ? money(closingBalance) : money(net), sub: hasBalanceData && openingBalance !== null ? `Opened at ${money(openingBalance)}` : savingsRate > 0 ? `${savingsRate}% of income saved` : "—" },
            { name: "Savings rate",   val: `${savingsRate}%`, sub: "This period" },
            { name: "Spending",       val: money(expenses),   sub: `${pieRows.length} categories` },
            { name: "Top category",   val: topCat,            sub: money(byCategory[topCat] || 0) },
          ].map(({ name, val, sub }) => (
            <div className="card account-card" key={name}>
              <div className="account-card-header"><span className="account-label">{name}</span></div>
              <div className="account-amount">{val}</div>
              <div className="account-change muted">{sub}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LedgerMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M6 5v10h4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d="M12 11.5h3M12 15h3" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}
