import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, money, EXPENSE_CATEGORIES, CATEGORY_COLORS, KEYS } from "../lib";
import { useToast, CardSkeleton, QueryGate } from "../components/ui";
import { Target, AlertCircle, Sparkles, CheckCircle } from "lucide-react";

export default function Budgets() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [draft, setDraft]       = React.useState({});
  const [saving, setSaving]     = React.useState(false);

  const budgetsQuery = useQuery({ queryKey: KEYS.budgets(), queryFn: () => apiFetch("/budgets") });
  const summaryQuery = useQuery({ queryKey: KEYS.summary("this_month"), queryFn: () => apiFetch("/summary?range=this_month") });

  // Re-sync the editable draft whenever the server's budget list changes
  // (initial load, or after saving/applying suggestions).
  React.useEffect(() => {
    if (!budgetsQuery.data) return;
    setDraft(Object.fromEntries(budgetsQuery.data.map((b) => [b.category, Number(b.monthly_limit)])));
  }, [budgetsQuery.data]);

  const byCategory = summaryQuery.data?.by_category || {};

  async function saveBudgets() {
    setSaving(true);
    try {
      const payload = EXPENSE_CATEGORIES.map((cat) => ({
        category: cat,
        monthly_limit: Number(draft[cat] || 0),
        strategy: "manual",
      }));
      await apiFetch("/budgets", { method: "PUT", body: JSON.stringify(payload) });
      queryClient.invalidateQueries({ queryKey: KEYS.budgets() });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
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
      await apiFetch("/budgets", { method: "PUT", body: JSON.stringify(suggestions) });
      queryClient.invalidateQueries({ queryKey: KEYS.budgets() });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
      toast("Dynamic budgets applied", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  const skeleton = (
    <div className="view-budgets">
      <h1 className="page-title">Goals & Budgets</h1>
      <p className="page-subtitle">Loading your budgets…</p>
      <div className="budget-grid">
        {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
      </div>
    </div>
  );

  if (budgetsQuery.isLoading || summaryQuery.isLoading || budgetsQuery.isError || summaryQuery.isError) {
    return (
      <QueryGate
        loading={budgetsQuery.isLoading || summaryQuery.isLoading}
        error={budgetsQuery.error || summaryQuery.error}
        onRetry={() => { budgetsQuery.refetch(); summaryQuery.refetch(); }}
        skeleton={skeleton}
      />
    );
  }

  const totalBudgeted = EXPENSE_CATEGORIES.reduce((s, c) => s + (Number(draft[c]) || 0), 0);
  const totalSpent    = EXPENSE_CATEGORIES.reduce((s, c) => s + Number(byCategory[c] || 0), 0);
  const overCount     = EXPENSE_CATEGORIES.filter(c => {
    const b = Number(draft[c] || 0); return b > 0 && Number(byCategory[c] || 0) > b;
  }).length;

  return (
    <div className="view-budgets">
      <div className="view-header">
        <div>
          <h1 className="page-title">Goals & Budgets</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Track spending limits and stay on budget</p>
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
        {EXPENSE_CATEGORIES.map((cat) => {
          const spent  = Number(byCategory[cat] || 0);
          const budget = Number(draft[cat] || 0);
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
            </div>
          );
        })}
      </div>
    </div>
  );
}
