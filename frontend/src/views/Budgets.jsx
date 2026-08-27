import React from "react";
import { apiFetch, money, EXPENSE_CATEGORIES, CATEGORY_COLORS } from "../lib";
import { useToast, CardSkeleton } from "../components/ui";
import { Target, AlertCircle, Sparkles, CheckCircle } from "lucide-react";

export default function Budgets() {
  const toast = useToast();
  const [budgets, setBudgets]   = React.useState([]);
  const [summary, setSummary]   = React.useState(null);
  const [draft, setDraft]       = React.useState({});
  const [loading, setLoading]   = React.useState(true);
  const [saving, setSaving]     = React.useState(false);

  async function load() {
    setLoading(true);
    try {
      const [bud, sum] = await Promise.all([
        apiFetch("/budgets"),
        apiFetch("/summary?range=this_month"),
      ]);
      setBudgets(bud);
      setSummary(sum);
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
      const payload = EXPENSE_CATEGORIES.map((cat) => ({
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

  const totalBudgeted = EXPENSE_CATEGORIES.reduce((s, c) => s + (Number(draft[c]) || 0), 0);
  const totalSpent    = EXPENSE_CATEGORIES.reduce((s, c) => s + Number(byCategory[c] || 0), 0);
  const overCount     = EXPENSE_CATEGORIES.filter(c => {
    const b = Number(draft[c] || 0); return b > 0 && Number(byCategory[c] || 0) > b;
  }).length;

  return (
    <div className="view-budgets">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 32 }}>
        <div>
          <h1 className="page-title">Goals & Budgets</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Track spending limits and stay on budget</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn-secondary" style={{ fontSize: 14 }} onClick={applyDynamic}>
            <Sparkles size={15} /> AI Suggestions
          </button>
          <button className="btn-primary" onClick={saveBudgets} disabled={saving}>
            <CheckCircle size={15} /> {saving ? "Saving…" : "Save Budgets"}
          </button>
        </div>
      </div>

      {/* Summary row */}
      <div className="budget-summary-row">
        {[
          { label: 'Total Budgeted', val: money(totalBudgeted), color: 'var(--accent)' },
          { label: 'Total Spent',    val: money(totalSpent),    color: totalSpent > totalBudgeted ? 'var(--negative)' : 'var(--positive)' },
          { label: 'Over Budget',    val: `${overCount} categories`, color: overCount > 0 ? 'var(--negative)' : 'var(--positive)' },
        ].map(({ label, val, color }) => (
          <div className="card" key={label} style={{ padding: '20px 24px' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>{label}</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700, color }}>{val}</div>
          </div>
        ))}
      </div>

      <div className="budget-grid">
        {EXPENSE_CATEGORIES.map((cat) => {
          const spent  = Number(byCategory[cat] || 0);
          const budget = Number(draft[cat] || 0);
          const pct    = budget > 0 ? Math.min(120, (spent / budget) * 100) : 0;
          const isOver = budget > 0 && spent > budget;
          const color  = CATEGORY_COLORS[cat] || "#9ca3af";

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
            </div>
          );
        })}
      </div>
    </div>
  );
}
