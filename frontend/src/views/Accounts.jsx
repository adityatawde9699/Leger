import React from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import { Plus, CreditCard, Wallet, Building2, PiggyBank, Trash2 } from "lucide-react";

const ICONS = {
  savings: <PiggyBank size={20} />,
  current: <Building2 size={20} />,
  credit: <CreditCard size={20} />,
  wallet: <Wallet size={20} />,
  cash: <Wallet size={20} />,
};

const COLORS = {
  savings: "#10b981",
  current: "#3b82f6",
  credit: "#f97316",
  wallet: "#a855f7",
  cash: "#6b7280",
};

export default function Accounts() {
  const toast = useToast();
  const [accounts, setAccounts] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [showForm, setShowForm] = React.useState(false);
  const [form, setForm] = React.useState({
    name: "", account_type: "savings", institution: "", balance: "", currency: "INR",
  });
  const [saving, setSaving] = React.useState(false);

  async function load() {
    try {
      const data = await apiFetch("/accounts");
      setAccounts(data);
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

  const totalBalance = accounts.reduce((s, a) => s + Number(a.balance || 0), 0);

  return (
    <div className="view-accounts">
      <div className="page-title-block">
        <h1 className="page-title">Accounts</h1>
        <p className="page-subtitle">Manage your bank accounts, wallets, and cards</p>
      </div>

      {/* Total balance card */}
      <div className="card hero-card" style={{ marginBottom: 20 }}>
        <div className="hero-label"><Wallet size={15} /> Total Balance</div>
        <div className="hero-amount">{money(totalBalance)}</div>
        <div className="hero-change positive">{accounts.length} active accounts</div>
      </div>

      {/* Account cards */}
      <div className="account-grid" style={{ marginBottom: 20 }}>
        {loading && Array.from({ length: 3 }).map((_, i) => (
          <div className="card" key={i}>
            <div className="skeleton" style={{ height: 20, width: "60%", borderRadius: 4, marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 30, width: "40%", borderRadius: 4 }} />
          </div>
        ))}
        {!loading && accounts.map((acct) => (
          <div className="card account-detail-card" key={acct.id}>
            <div className="account-card-header">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div className="account-type-icon" style={{ color: COLORS[acct.account_type] }}>
                  {ICONS[acct.account_type]}
                </div>
                <div>
                  <div className="account-detail-name">{acct.name}</div>
                  <div className="account-detail-type">{acct.institution || acct.account_type}</div>
                </div>
              </div>
              <button className="tx-delete-btn" onClick={() => remove(acct.id)} aria-label={`Remove ${acct.name}`}>
                <Trash2 size={13} />
              </button>
            </div>
            <div className="account-amount" style={{ color: COLORS[acct.account_type] }}>
              {money(acct.balance)}
            </div>
            <div className="account-change muted">{acct.currency} · {acct.account_type}</div>
          </div>
        ))}
      </div>

      {/* Add account */}
      {!showForm ? (
        <button className="btn-primary" onClick={() => setShowForm(true)} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Plus size={14} /> Add Account
        </button>
      ) : (
        <div className="card" style={{ marginTop: 12 }}>
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
                <label className="form-label">Balance</label>
                <div className="input-prefix-wrap">
                  <span className="input-prefix">₹</span>
                  <input type="number" placeholder="0" value={form.balance}
                    onChange={(e) => setForm({ ...form, balance: e.target.value })} />
                </div>
              </div>
            </div>
            <div className="form-actions">
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
