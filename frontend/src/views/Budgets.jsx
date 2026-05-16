import React from "react";
import { apiFetch, money, EXPENSE_CATEGORIES, CATEGORY_COLORS } from "../lib";
import { useToast, CardSkeleton } from "../components/ui";
import { Target, AlertCircle } from "lucide-react";

export default function Budgets() {
  const toast = useToast();
  const [budgets, setBudgets] = React.useState([]);
  const [summary, setSummary] = React.useState(null);
  const [draft, setDraft] = React.useState({});
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);

  async function load() {
    setLoading(true);
    try {
      const [bud, sum] = await Promise.all([
        apiFetch("/budgets"),
        apiFetch("/summary"),
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

  const budgetMap = Object.fromEntries(budgets.map((b) => [b.category, Number(b.monthly_limit)]));
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
        <div className="page-title-block">
          <h1 className="page-title">Goals & Budgets</h1>
        </div>
        <div className="budget-grid">
          {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      </div>
    );
  }

  return (
    <div className="view-budgets">
      <div className="page-title-block">
        <h1 className="page-title">Goals & Budgets</h1>
        <p className="page-subtitle">Track spending limits and stay on budget</p>
      </div>

      <div className="section-block">
        <div className="section-header">
          <div className="section-header-left"><Target size={18} /> Budget Tracking</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-secondary" style={{ fontSize: 13, padding: "8px 14px" }}
              onClick={applyDynamic}>
              Use 3-month dynamic
            </button>
            <button className="btn-add" onClick={saveBudgets} disabled={saving}>
              {saving ? "Saving…" : "Save Budgets"}
            </button>
          </div>
        </div>

        <div className="budget-grid">
          {EXPENSE_CATEGORIES.map((cat) => {
            const spent = Number(byCategory[cat] || 0);
            const budget = draft[cat] || 0;
            const pct = budget ? Math.min(120, (spent / budget) * 100) : 0;
            const isOver = budget > 0 && spent > budget;
            const color = CATEGORY_COLORS[cat] || "#9ca3af";

            return (
              <div className={`card budget-card${isOver ? " over-budget" : ""}`} key={cat}>
                <div className="budget-card-top">
                  <div className="budget-cat-name" style={{ color }}>{cat}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span className="budget-period">Monthly</span>
                    {isOver && <AlertCircle size={14} className="budget-over-icon" />}
                  </div>
                </div>
                <div className="budget-progress-label">
                  <span>Progress</span>
                  <span className={`budget-progress-pct${isOver ? " over" : ""}`}>
                    {Math.round(pct)}%
                  </span>
                </div>
                <div className="progress-bar-track">
                  <div
                    className={`progress-bar-fill${isOver ? " over" : ""}`}
                    style={{
                      width: `${Math.min(100, pct)}%`,
                      background: isOver ? "#ef4444" : color,
                    }}
                  />
                </div>
                {isOver && (
                  <div className="budget-over-msg">Over by {money(spent - budget)}</div>
                )}
                <div className="budget-stats">
                  <div>
                    <div className="budget-stat-label">Spent</div>
                    <div className={`budget-stat-value${isOver ? " over" : ""}`}>{money(spent)}</div>
                  </div>
                  <div>
                    <div className="budget-stat-label">Limit</div>
                    <input
                      type="number" min="0" placeholder="Set budget"
                      value={draft[cat] ?? ""}
                      onChange={(e) => setDraft({ ...draft, [cat]: e.target.value })}
                      style={{ padding: "4px 8px", fontSize: 14, marginTop: 2 }}
                    />
                  </div>
                </div>
                <div className={`budget-remaining${isOver ? " over" : " ok"}`}>
                  {isOver
                    ? `${money(spent - budget)} over budget`
                    : budget > 0 ? `${money(Math.max(0, budget - spent))} remaining` : "No limit set"
                  }
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
