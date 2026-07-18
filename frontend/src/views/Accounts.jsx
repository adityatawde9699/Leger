import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, money, KEYS } from "../lib";
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
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = React.useState(false);
  const [form, setForm] = React.useState({
    name: "", account_type: "savings", institution: "", balance: "", currency: "INR",
  });
  const [saving, setSaving] = React.useState(false);

  const accountsQuery = useQuery({ queryKey: KEYS.accounts(), queryFn: () => apiFetch("/accounts") });
  const accounts = accountsQuery.data || [];
  const loading = accountsQuery.isLoading;

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
      queryClient.invalidateQueries({ queryKey: KEYS.accounts() });
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
      queryClient.invalidateQueries({ queryKey: KEYS.accounts() });
      toast("Account removed", "success");
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
              </div>
            );
          })}
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
