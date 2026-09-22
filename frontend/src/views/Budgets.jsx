import React from "react";
import { apiFetch, money, CATEGORY_COLORS } from "../lib";
import { useToast, CardSkeleton } from "../components/ui";
import { Target, AlertCircle, Sparkles, CheckCircle } from "lucide-react";

export default function Budgets() {
  const toast = useToast();
  const [budgets, setBudgets]   = React.useState([]);
  const [summary, setSummary]   = React.useState(null);
  const [draft, setDraft]       = React.useState({});
  const [loading, setLoading]   = React.useState(true);
  const [saving, setSaving]     = React.useState(false);
  const [categories, setCategories] = React.useState([]);

  async function load() {
    setLoading(true);
    try {
      const [bud, sum, cats] = await Promise.all([
        apiFetch("/budgets"),
        apiFetch("/summary?range=this_month"),
        apiFetch("/categories"),
      ]);
      setBudgets(bud);
      setSummary(sum);
      setCategories(Array.isArray(cats) ? cats.filter((item) => item.is_active && item.kind === "expense").map((item) => item.name) : []);
      setDraft(Object.fromEntries(bud.map((b) => [b.category, Number(b.monthly_limit)])));
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => { load(); }, []);

  const byCategory = summary?.by_category || {};

  async function saveBudgets() {
    setSaving(true);
    try {
      const payload = budgetCategories.map((cat) => ({
        category: cat,
        monthly_limit: Number(draft[cat] || 0),
        strategy: "manual",
      }));
      const saved = await apiFetch("/budgets", { method: "PUT", body: JSON.stringify(payload) });
      setBudgets(saved);
      toast("Budgets saved", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function applyDynamic() {
    try {
      const suggestions = await apiFetch("/budgets/suggestions");
      const saved = await apiFetch("/budgets", { method: "PUT", body: JSON.stringify(suggestions) });
      setBudgets(saved);
      setDraft(Object.fromEntries(saved.map((b) => [b.category, Number(b.monthly_limit)])));
      setCategories((items) => [...new Set([...items, ...saved.map((item) => item.category)])]);
      toast("Dynamic budgets applied", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  if (loading) {
    return (
      <div className="view-budgets">
        <h1 className="page-title">Goals & Budgets</h1>
        <p className="page-subtitle">Loading your budgets…</p>
        <div className="budget-grid">
          {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      </div>
    );
  }

  const budgetCategories = [...new Set([...categories, ...budgets.map((budget) => budget.category), ...Object.keys(byCategory)])].sort();
  const totalBudgeted = budgetCategories.reduce((s, c) => s + (Number(draft[c]) || 0), 0);
  const totalSpent    = budgetCategories.reduce((s, c) => s + Number(byCategory[c] || 0), 0);
  const overCount     = budgetCategories.filter(c => {
    const b = Number(draft[c] || 0); return b > 0 && Number(byCategory[c] || 0) > b;
  }).length;

  return (
    <div className="view-budgets">
      <div className="view-header">
        <div>
          <h1 className="page-title">Goals & Budgets</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Set a target, see your pace, and decide what to adjust.</p>
        </div>
        <div className="view-header-actions">
          <button className="btn-secondary" style={{ fontSize: 14 }} onClick={applyDynamic}>
            <Sparkles size={15} /> AI Suggestions
          </button>
          <button className="btn-primary" onClick={saveBudgets} disabled={saving}>
            <CheckCircle size={15} /> {saving ? "Saving…" : "Save Budgets"}
          </button>
        </div>
      </div>

      <p style={{ color: "var(--text-muted)", fontSize: 12, margin: "-8px 0 18px" }}>
        Pace projections extend spending so far this month across the full month. They are estimates, not a forecast of bills or account balance.
      </p>

      {/* Summary strip */}
      <div className="summary-strip">
        {[
          { label: 'Total Budgeted', val: money(totalBudgeted), color: 'var(--text-primary)' },
          { label: 'Total Spent',    val: money(totalSpent),    color: totalSpent > totalBudgeted ? 'var(--negative)' : 'var(--primary)' },
          { label: 'Over Budget',    val: `${overCount} categories`, color: overCount > 0 ? 'var(--negative)' : 'var(--primary)' },
        ].map(({ label, val, color }) => (
          <div className="stat-card" key={label}>
            <div className="stat-card-label">{label}</div>
            <div className="stat-card-value" style={{ color }}>{val}</div>
          </div>
        ))}
      </div>

      <div className="budget-grid">
        {budgetCategories.map((cat) => {
          const spent  = Number(byCategory[cat] || 0);
          const budget = Number(draft[cat] || 0);
          const now = new Date();
          const dayOfMonth = now.getDate();
          const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
          const projected = dayOfMonth ? spent / dayOfMonth * daysInMonth : spent;
          const remainingDays = Math.max(1, daysInMonth - dayOfMonth);
          const dailyAllowance = budget > 0 ? Math.max(0, budget - spent) / remainingDays : null;
          const pct    = budget > 0 ? Math.min(120, (spent / budget) * 100) : 0;
          const isOver = budget > 0 && spent > budget;
          const color  = CATEGORY_COLORS[cat] || "var(--text-secondary)";

          return (
            <div className={`card budget-card${isOver ? " over-budget" : ""}`} key={cat}>
              <div className="budget-card-top">
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
                  <div className="budget-cat-name" style={{ color: isOver ? 'var(--negative)' : 'var(--text-primary)' }}>{cat}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="budget-period">Monthly</span>
                  {isOver && <AlertCircle size={16} style={{ color: 'var(--negative)' }} />}
                </div>
              </div>

              <div className="budget-progress-label">
                <span style={{ color: 'var(--text-secondary)' }}>
                  {money(spent)} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>of {budget > 0 ? money(budget) : "—"}</span>
                </span>
                <span style={{ color: isOver ? 'var(--negative)' : pct > 80 ? 'var(--warning)' : 'var(--text-secondary)' }}>
                  {budget > 0 ? `${Math.round(pct)}%` : "No limit"}
                </span>
              </div>

              <div className="progress-bar-track">
                <div
                  className="progress-bar-fill"
                  style={{
                    width: `${Math.min(100, pct)}%`,
                    background: isOver ? 'var(--negative)' : pct > 80 ? 'var(--warning)' : color,
                  }}
                />
              </div>

              {isOver && (
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--negative)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertCircle size={13} /> Over by {money(spent - budget)}
                </div>
              )}

              <div className="budget-stats">
                <div>
                  <div className="budget-stat-label">Spent</div>
                  <div className="budget-stat-value" style={{ color: isOver ? 'var(--negative)' : 'var(--text-primary)' }}>{money(spent)}</div>
                </div>
                <div>
                  <div className="budget-stat-label">Monthly Limit</div>
                  <div className="input-prefix-wrap">
                    <span className="input-prefix" style={{ top: 'unset', transform: 'none', position: 'relative', left: 'unset', marginRight: 4, fontSize: 14, fontWeight: 700 }}>₹</span>
                    <input
                      type="number" min="0" placeholder="Set limit"
                      value={draft[cat] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [cat]: e.target.value })}
                      style={{ padding: '6px 10px', fontSize: 15, fontWeight: 600, display: 'inline-block', width: 'calc(100% - 20px)' }}
                    />
                  </div>
                </div>
              </div>

              <div className={`budget-remaining ${isOver ? "over" : "ok"}`}>
                {isOver
                  ? <><AlertCircle size={14} /> {money(spent - budget)} over budget</>
                  : budget > 0
                    ? <><CheckCircle size={14} /> {money(Math.max(0, budget - spent))} remaining</>
                    : "No limit set"
                }
              </div>
              {budget > 0 && spent > 0 && (
                <div style={{ borderTop: "1px solid var(--border)", marginTop: 12, paddingTop: 10, fontSize: 11, lineHeight: 1.5, color: projected > budget ? "var(--warning)" : "var(--text-muted)" }}>
                  At this month’s pace: about {money(projected)} by month end.
                  {dailyAllowance != null && <span> To stay near your target, average {money(dailyAllowance)}/day for the remaining {remainingDays} days.</span>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
