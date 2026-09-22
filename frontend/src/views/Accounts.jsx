import React from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import { Plus, CreditCard, Wallet, Building2, PiggyBank, Trash2, ChevronRight } from "lucide-react";

const ICONS = {
  savings: PiggyBank,
  current: Building2,
  credit:  CreditCard,
  wallet:  Wallet,
  cash:    Wallet,
};

const COLORS = {
  savings: "var(--positive)",
  current: "var(--info)",
  credit:  "var(--warning)",
  wallet:  "var(--info)",
  cash:    "var(--text-secondary)",
};

const BG_COLORS = {
  savings: "var(--positive-soft)",
  current: "rgba(56,189,248,0.12)",
  credit:  "rgba(250,204,21,0.12)",
  wallet:  "rgba(56,189,248,0.12)",
  cash:    "var(--surface-secondary)",
};

export default function Accounts() {
  const toast = useToast();
  const [accounts, setAccounts] = React.useState([]);
  const [loading,  setLoading]  = React.useState(true);
  const [showForm, setShowForm] = React.useState(false);
  const [reconcileId, setReconcileId] = React.useState(null);
  const [reconcileForm, setReconcileForm] = React.useState({ observed_balance: "", note: "" });
  const [form, setForm] = React.useState({
    name: "", account_type: "savings", institution: "", balance: "", currency: "INR",
  });
  const [saving, setSaving] = React.useState(false);

  async function load() {
    try {
      setAccounts(await apiFetch("/accounts"));
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => { load(); }, []);

  async function create(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/accounts", {
        method: "POST",
        body: JSON.stringify({ ...form, balance: Number(form.balance || 0) }),
      });
      setForm({ name: "", account_type: "savings", institution: "", balance: "", currency: "INR" });
      setShowForm(false);
      await load();
      toast("Account added", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id) {
    try {
      await apiFetch(`/accounts/${id}`, { method: "DELETE" });
      setAccounts((a) => a.filter((x) => x.id !== id));
      toast("Account removed", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function reconcile(e) {
    e.preventDefault();
    if (!reconcileId || reconcileForm.observed_balance === "") return;
    try {
      const result = await apiFetch(`/accounts/${reconcileId}/reconcile`, {
        method: "POST",
        body: JSON.stringify({
          observed_balance: Number(reconcileForm.observed_balance),
          note: reconcileForm.note.trim() || null,
        }),
      });
      setAccounts((current) => current.map((account) => account.id === reconcileId
        ? { ...account, balance: result.observed_balance, last_reconciled_at: result.reconciled_at, last_reconciled_balance: result.observed_balance, reconciliation_note: result.note }
        : account));
      toast(result.difference === 0 ? "Account reconciled" : `Balance updated · difference ${money(result.difference)}`, "success");
      setReconcileId(null);
      setReconcileForm({ observed_balance: "", note: "" });
    } catch (e) {
      toast(e.message, "error");
    }
  }

  const totalBalance = accounts.reduce((s, a) => s + Number(a.balance || 0), 0);

  return (
    <div className="view-accounts">
      <div className="view-header">
        <div>
          <h1 className="page-title">Accounts</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Manage your bank accounts, wallets, and cards</p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={16} /> Add Account
        </button>
      </div>

      {/* Hero */}
      <div className="card hero-card" style={{ marginBottom: 24 }}>
        <div className="hero-label"><Wallet size={16} /> Total Balance Across All Accounts</div>
        <div className="hero-amount">{money(totalBalance)}</div>
        <div className="hero-change positive">{accounts.length} active account{accounts.length !== 1 ? "s" : ""}</div>
      </div>

      {/* Account cards */}
      {loading ? (
        <div className="account-grid">
          {Array.from({ length: 3 }).map((_, i) => (
            <div className="card" key={i} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="skeleton" style={{ height: 14, width: '50%', borderRadius: 6 }} />
              <div className="skeleton" style={{ height: 30, width: '70%', borderRadius: 6 }} />
              <div className="skeleton" style={{ height: 12, width: '35%', borderRadius: 6 }} />
            </div>
          ))}
        </div>
      ) : accounts.length === 0 ? (
        <div className="card empty-state">
          <div className="empty-state-emoji">🏦</div>
          <div className="empty-state-title">No accounts yet</div>
          <div className="empty-state-text">Add your first account to start tracking</div>
        </div>
      ) : (
        <div className="account-grid" style={{ marginBottom: 24 }}>
          {accounts.map((acct) => {
            const IconComp = ICONS[acct.account_type] || Wallet;
            const color    = COLORS[acct.account_type] || 'var(--text-secondary)';
            const bg       = BG_COLORS[acct.account_type] || 'var(--surface-secondary)';
            return (
              <div className="card account-card" key={acct.id}
                style={{ borderTop: `3px solid ${color}` }}>
                <div className="account-card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div className="icon-chip" style={{ background: bg, color }}>
                      <IconComp size={22} />
                    </div>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{acct.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, textTransform: 'capitalize' }}>
                        {acct.institution || acct.account_type}
                      </div>
                    </div>
                  </div>
                  <button className="tx-delete-btn" onClick={() => remove(acct.id)} aria-label={`Remove ${acct.name}`}>
                    <Trash2 size={14} />
                  </button>
                </div>
                <div className="num" style={{ fontSize: 30, fontWeight: 600, color, marginTop: 4 }}>
                  {money(acct.balance)}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.05em' }}>
                  {acct.currency} · {acct.account_type.toUpperCase()}
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginTop: 14 }}>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {acct.last_reconciled_at ? `Checked ${new Date(acct.last_reconciled_at).toLocaleDateString("en-IN")}` : "Not reconciled"}
                  </span>
                  <button className="btn-secondary" style={{ padding: "5px 9px", fontSize: 11 }} onClick={() => {
                    setReconcileId(acct.id);
                    setReconcileForm({ observed_balance: String(acct.balance ?? ""), note: acct.reconciliation_note || "" });
                  }}>Reconcile</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {reconcileId && (
        <div className="card" style={{ marginTop: 8, marginBottom: 24 }}>
          <div className="form-section-title">Reconcile account</div>
          <p style={{ margin: "-4px 0 16px", color: "var(--text-muted)", fontSize: 13 }}>
            Enter the balance shown by your bank, wallet, or card. Ledger will record the difference and update the account balance.
          </p>
          <form onSubmit={reconcile}>
            <div className="form-grid-2">
              <div className="form-field">
                <label className="form-label">Observed balance</label>
                <div className="input-prefix-wrap"><span className="input-prefix">₹</span>
                  <input required type="number" step="0.01" value={reconcileForm.observed_balance} onChange={(e) => setReconcileForm({ ...reconcileForm, observed_balance: e.target.value })} />
                </div>
              </div>
              <div className="form-field">
                <label className="form-label">Note</label>
                <input placeholder="e.g. Checked after September statement" value={reconcileForm.note} onChange={(e) => setReconcileForm({ ...reconcileForm, note: e.target.value })} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
              <button type="submit" className="btn-primary">Save reconciliation</button>
              <button type="button" className="btn-secondary" onClick={() => setReconcileId(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Add form */}
      {showForm && (
        <div className="card" style={{ marginTop: 8 }}>
          <div className="form-section-title">New Account</div>
          <form onSubmit={create}>
            <div className="form-grid-2">
              <div className="form-field">
                <label className="form-label">Account Name</label>
                <input required placeholder="e.g. HDFC Savings" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="form-field">
                <label className="form-label">Type</label>
                <select value={form.account_type}
                  onChange={(e) => setForm({ ...form, account_type: e.target.value })}>
                  <option value="savings">Savings</option>
                  <option value="current">Current</option>
                  <option value="credit">Credit Card</option>
                  <option value="wallet">Wallet</option>
                  <option value="cash">Cash</option>
                </select>
              </div>
            </div>
            <div className="form-grid-2">
              <div className="form-field">
                <label className="form-label">Institution</label>
                <input placeholder="e.g. HDFC Bank" value={form.institution}
                  onChange={(e) => setForm({ ...form, institution: e.target.value })} />
              </div>
              <div className="form-field">
                <label className="form-label">Opening Balance</label>
                <div className="input-prefix-wrap">
                  <span className="input-prefix">₹</span>
                  <input type="number" placeholder="0" value={form.balance}
                    onChange={(e) => setForm({ ...form, balance: e.target.value })} />
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? "Adding…" : "Add Account"}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
