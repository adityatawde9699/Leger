import React from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import { CheckCircle2, Pause, Play, Plus, Target, Trash2 } from "lucide-react";

const GOAL_TYPES = [
  ["emergency_fund", "Emergency fund"],
  ["debt_payoff", "Debt payoff"],
  ["savings", "Savings"],
  ["spending_reduction", "Spending reduction"],
  ["custom", "Custom goal"],
];

const emptyForm = { name: "", goal_type: "savings", target_amount: "", current_amount: "0", deadline: "", status: "active" };

function progress(goal) {
  return Math.min(100, Math.max(0, Number(goal.target_amount) > 0 ? Number(goal.current_amount) / Number(goal.target_amount) * 100 : 0));
}

function monthlyNeed(goal) {
  const remaining = Math.max(0, Number(goal.target_amount) - Number(goal.current_amount));
  if (!remaining || !goal.deadline) return null;
  const days = Math.max(1, Math.ceil((new Date(`${goal.deadline}T00:00:00`) - new Date()) / 86400000));
  return remaining / Math.max(1, days / 30.44);
}

export default function Goals() {
  const toast = useToast();
  const [goals, setGoals] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  const [form, setForm] = React.useState(emptyForm);
  const [saving, setSaving] = React.useState(false);

  const load = React.useCallback(async () => {
    try { setGoals(await apiFetch("/goals")); }
    catch (e) { toast(e.message, "error"); }
    finally { setLoading(false); }
  }, [toast]);

  React.useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditing(null); setForm(emptyForm); setShowForm(true); };
  const openEdit = (goal) => {
    setEditing(goal.id);
    setForm({ name: goal.name, goal_type: goal.goal_type, target_amount: String(goal.target_amount), current_amount: String(goal.current_amount), deadline: goal.deadline || "", status: goal.status });
    setShowForm(true);
  };

  async function save(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...form, target_amount: Number(form.target_amount), current_amount: Number(form.current_amount), deadline: form.deadline || null };
      const saved = await apiFetch(editing ? `/goals/${editing}` : "/goals", { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) });
      setGoals((current) => editing ? current.map((goal) => goal.id === editing ? saved : goal) : [...current, saved]);
      setShowForm(false);
      toast(editing ? "Goal updated" : "Goal created", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  }

  async function toggleStatus(goal) {
    const status = goal.status === "active" ? "paused" : "active";
    try {
      const saved = await apiFetch(`/goals/${goal.id}`, { method: "PUT", body: JSON.stringify({ ...goal, target_amount: Number(goal.target_amount), current_amount: Number(goal.current_amount), status }) });
      setGoals((current) => current.map((item) => item.id === goal.id ? saved : item));
    } catch (e) { toast(e.message, "error"); }
  }

  async function remove(goal) {
    if (!window.confirm(`Delete “${goal.name}”?`)) return;
    try { await apiFetch(`/goals/${goal.id}`, { method: "DELETE" }); setGoals((current) => current.filter((item) => item.id !== goal.id)); }
    catch (e) { toast(e.message, "error"); }
  }

  const activeGoals = goals.filter((goal) => goal.status === "active");
  const completedGoals = goals.filter((goal) => goal.status === "completed");

  return (
    <div className="view-accounts">
      <div className="view-header">
        <div>
          <h1 className="page-title">Goals</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Turn a financial intention into a visible next step.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}><Plus size={16} /> New goal</button>
      </div>

      {activeGoals.length > 0 && (
        <div className="account-grid" style={{ marginBottom: 24 }}>
          {activeGoals.map((goal) => {
            const pct = progress(goal);
            const needed = monthlyNeed(goal);
            return (
              <div className="card" key={goal.id} style={{ borderTop: "3px solid var(--primary)" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <div className="icon-chip" style={{ background: "var(--positive-soft)", color: "var(--primary)" }}><Target size={21} /></div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, color: "var(--text-primary)" }}>{goal.name}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{GOAL_TYPES.find(([value]) => value === goal.goal_type)?.[1] || "Goal"}</div>
                  </div>
                  <button className="tx-delete-btn" onClick={() => remove(goal)} aria-label={`Delete ${goal.name}`}><Trash2 size={14} /></button>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 20 }}>
                  <span style={{ fontSize: 24, fontWeight: 700, color: "var(--text-primary)" }}>{money(goal.current_amount)}</span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>of {money(goal.target_amount)}</span>
                </div>
                <div style={{ height: 9, background: "var(--surface-secondary)", borderRadius: 99, overflow: "hidden", marginTop: 10 }}>
                  <div style={{ height: "100%", width: `${pct}%`, background: "var(--primary)", borderRadius: 99 }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>
                  <span>{pct.toFixed(0)}% complete</span>
                  <span>{goal.deadline ? `Due ${goal.deadline}` : "No deadline"}</span>
                </div>
                {needed != null && <div style={{ marginTop: 12, fontSize: 12, color: "var(--text-secondary)" }}>Aim for about <strong>{money(needed)}/month</strong> to reach this goal.</div>}
                <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                  <button className="btn-secondary" style={{ padding: "6px 10px", fontSize: 12 }} onClick={() => openEdit(goal)}>Update progress</button>
                  <button className="btn-secondary" style={{ padding: "6px 10px", fontSize: 12 }} onClick={() => toggleStatus(goal)}><Pause size={13} /> Pause</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && !goals.length && (
        <div className="card empty-state"><div className="empty-state-emoji">🎯</div><div className="empty-state-title">No goals yet</div><div className="empty-state-text">Start with one target—an emergency fund, debt payoff, or savings milestone.</div><button className="btn-primary" onClick={openCreate}><Plus size={15} /> Create your first goal</button></div>
      )}

      {completedGoals.length > 0 && <div className="card" style={{ marginBottom: 24 }}><div className="chart-title" style={{ display: "flex", gap: 8, alignItems: "center" }}><CheckCircle2 size={17} style={{ color: "var(--positive)" }} /> Completed goals</div>{completedGoals.map((goal) => <div key={goal.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 0", borderBottom: "1px solid var(--border)" }}><CheckCircle2 size={15} style={{ color: "var(--positive)" }} /><span style={{ flex: 1, color: "var(--text-primary)" }}>{goal.name}</span><span style={{ fontSize: 12, color: "var(--text-muted)" }}>{money(goal.current_amount)} / {money(goal.target_amount)}</span><button className="tx-delete-btn" onClick={() => remove(goal)} aria-label={`Delete ${goal.name}`}><Trash2 size={13} /></button></div>)}</div>}

      {goals.filter((goal) => goal.status === "paused").map((goal) => <div className="card" key={goal.id} style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12 }}><Pause size={16} style={{ color: "var(--warning)" }} /><span style={{ flex: 1 }}>{goal.name} · {money(goal.current_amount)} / {money(goal.target_amount)}</span><button className="btn-secondary" style={{ padding: "6px 10px", fontSize: 12 }} onClick={() => toggleStatus(goal)}><Play size={13} /> Resume</button></div>)}

      {showForm && <div className="card" style={{ marginTop: 20 }}><div className="form-section-title">{editing ? "Update goal" : "New goal"}</div><form onSubmit={save}><div className="form-grid-2"><div className="form-field"><label className="form-label">Goal name</label><input required placeholder="e.g. Emergency fund" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div><div className="form-field"><label className="form-label">Type</label><select value={form.goal_type} onChange={(e) => setForm({ ...form, goal_type: e.target.value })}>{GOAL_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div><div className="form-grid-2"><div className="form-field"><label className="form-label">Target amount</label><input required type="number" min="0.01" step="0.01" value={form.target_amount} onChange={(e) => setForm({ ...form, target_amount: e.target.value })} /></div><div className="form-field"><label className="form-label">Current amount</label><input required type="number" min="0" step="0.01" value={form.current_amount} onChange={(e) => setForm({ ...form, current_amount: e.target.value })} /></div></div><div className="form-grid-2"><div className="form-field"><label className="form-label">Deadline (optional)</label><input type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} /></div></div><div style={{ display: "flex", gap: 12, marginTop: 8 }}><button className="btn-primary" type="submit" disabled={saving}>{saving ? "Saving…" : editing ? "Save changes" : "Create goal"}</button><button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button></div></form></div>}
    </div>
  );
}
