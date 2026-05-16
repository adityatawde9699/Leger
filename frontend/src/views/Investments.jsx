import React from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import {
  Briefcase, TrendingUp, TrendingDown, Plus, Trash2,
  BarChart3, PiggyBank, Bitcoin, Landmark, Award,
} from "lucide-react";

const TYPE_ICONS = {
  stocks: <BarChart3 size={20} />,
  mutual_funds: <PiggyBank size={20} />,
  crypto: <Bitcoin size={20} />,
  fixed_deposit: <Landmark size={20} />,
  gold: <Award size={20} />,
};
const TYPE_COLORS = {
  stocks: "#3b82f6", mutual_funds: "#10b981", crypto: "#f59e0b",
  fixed_deposit: "#6366f1", gold: "#eab308",
};

export default function Investments() {
  const toast = useToast();
  const [portfolios, setPortfolios] = React.useState([]);
  const [summary, setSummary] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [showForm, setShowForm] = React.useState(false);
  const [form, setForm] = React.useState({ name: "", portfolio_type: "stocks" });
  const [selected, setSelected] = React.useState(null);
  const [holdings, setHoldings] = React.useState([]);
  const [holdingForm, setHoldingForm] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  async function load() {
    try {
      const [p, s] = await Promise.all([
        apiFetch("/portfolios"),
        apiFetch("/portfolios/summary"),
      ]);
      setPortfolios(p);
      setSummary(s);
    } catch (e) { toast(e.message, "error"); }
    finally { setLoading(false); }
  }

  React.useEffect(() => { load(); }, []);

  async function selectPortfolio(p) {
    setSelected(p);
    try {
      setHoldings(await apiFetch(`/portfolios/${p.id}/holdings`));
    } catch (e) { toast(e.message, "error"); }
  }

  async function createPortfolio(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/portfolios", { method: "POST", body: JSON.stringify(form) });
      setForm({ name: "", portfolio_type: "stocks" });
      setShowForm(false);
      await load();
      toast("Portfolio created", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  }

  async function deletePortfolio(id) {
    try {
      await apiFetch(`/portfolios/${id}`, { method: "DELETE" });
      setPortfolios(p => p.filter(x => x.id !== id));
      if (selected?.id === id) { setSelected(null); setHoldings([]); }
      await load();
      toast("Portfolio deleted", "success");
    } catch (e) { toast(e.message, "error"); }
  }

  async function addHolding(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch(`/portfolios/${selected.id}/holdings`, {
        method: "POST",
        body: JSON.stringify({
          ...holdingForm,
          quantity: Number(holdingForm.quantity),
          buy_price: Number(holdingForm.buy_price),
          current_price: Number(holdingForm.current_price || 0),
        }),
      });
      setHoldingForm(null);
      setHoldings(await apiFetch(`/portfolios/${selected.id}/holdings`));
      await load();
      toast("Holding added", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  }

  async function deleteHolding(id) {
    try {
      await apiFetch(`/holdings/${id}`, { method: "DELETE" });
      setHoldings(h => h.filter(x => x.id !== id));
      await load();
      toast("Holding removed", "success");
    } catch (e) { toast(e.message, "error"); }
  }

  const pnlColor = (v) => v >= 0 ? "var(--positive)" : "var(--negative)";
  const pnlIcon = (v) => v >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />;

  return (
    <div className="view-investments">
      <div className="page-title-block">
        <h1 className="page-title">Investments</h1>
        <p className="page-subtitle">Track your portfolio, holdings, and returns</p>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="account-grid" style={{ marginBottom: 20 }}>
          <div className="card hero-card">
            <div className="hero-label"><Briefcase size={15} /> Total Invested</div>
            <div className="hero-amount">{money(summary.total_invested)}</div>
            <div className="hero-change muted">{summary.portfolio_count} portfolios</div>
          </div>
          <div className="card hero-card">
            <div className="hero-label">{pnlIcon(summary.total_pnl)} Current Value</div>
            <div className="hero-amount">{money(summary.total_current)}</div>
            <div className={`hero-change ${summary.total_pnl >= 0 ? "positive" : "negative"}`}>
              {summary.total_pnl >= 0 ? "+" : ""}{money(summary.total_pnl)} ({summary.total_pnl_pct}%)
            </div>
          </div>
        </div>
      )}

      {/* Portfolio list */}
      <div className="portfolio-grid" style={{ marginBottom: 20 }}>
        {portfolios.map(p => (
          <button
            key={p.id}
            className={`card portfolio-card${selected?.id === p.id ? " selected" : ""}`}
            onClick={() => selectPortfolio(p)}
          >
            <div className="portfolio-card-top">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div className="account-type-icon" style={{ color: TYPE_COLORS[p.portfolio_type] }}>
                  {TYPE_ICONS[p.portfolio_type]}
                </div>
                <div>
                  <div className="account-detail-name">{p.name}</div>
                  <div className="account-detail-type">{p.portfolio_type.replace(/_/g, " ")}</div>
                </div>
              </div>
              <button className="tx-delete-btn" onClick={(e) => { e.stopPropagation(); deletePortfolio(p.id); }}>
                <Trash2 size={13} />
              </button>
            </div>
          </button>
        ))}
      </div>

      {!showForm ? (
        <button className="btn-primary" onClick={() => setShowForm(true)} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 20 }}>
          <Plus size={14} /> Add Portfolio
        </button>
      ) : (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="form-section-title">New Portfolio</div>
          <form onSubmit={createPortfolio}>
            <div className="form-grid-2">
              <div className="form-field">
                <label className="form-label">Name</label>
                <input required placeholder="e.g. Long-term Stocks" value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="form-field">
                <label className="form-label">Type</label>
                <select value={form.portfolio_type} onChange={e => setForm({ ...form, portfolio_type: e.target.value })}>
                  <option value="stocks">Stocks</option>
                  <option value="mutual_funds">Mutual Funds</option>
                  <option value="crypto">Crypto</option>
                  <option value="fixed_deposit">Fixed Deposit</option>
                  <option value="gold">Gold</option>
                </select>
              </div>
            </div>
            <div className="form-actions">
              <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Creating…" : "Create"}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Holdings */}
      {selected && (
        <div className="card">
          <div className="form-section-title">{selected.name} — Holdings</div>
          {holdings.length === 0 ? (
            <div className="empty-state" style={{ padding: "30px 0" }}>
              <div className="empty-state-icon">📊</div>
              <div className="empty-state-title">No holdings yet</div>
              <div className="empty-state-sub">Add your first investment</div>
            </div>
          ) : (
            <div className="gst-table-wrap" style={{ marginBottom: 16 }}>
              <table className="gst-table">
                <thead>
                  <tr>
                    <th>Symbol</th><th>Name</th><th>Qty</th><th>Buy Price</th><th>Current</th><th>P&L</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map(h => {
                    const pnl = (Number(h.current_price) - Number(h.buy_price)) * Number(h.quantity);
                    const pnlPct = Number(h.buy_price) > 0 ? ((Number(h.current_price) - Number(h.buy_price)) / Number(h.buy_price) * 100).toFixed(1) : 0;
                    return (
                      <tr key={h.id}>
                        <td><strong>{h.symbol}</strong></td>
                        <td>{h.name}</td>
                        <td>{Number(h.quantity)}</td>
                        <td>{money(h.buy_price)}</td>
                        <td>{money(h.current_price)}</td>
                        <td style={{ color: pnlColor(pnl), fontWeight: 600 }}>
                          {pnl >= 0 ? "+" : ""}{money(pnl)} ({pnlPct}%)
                        </td>
                        <td>
                          <button className="tx-delete-btn" onClick={() => deleteHolding(h.id)}><Trash2 size={13} /></button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!holdingForm ? (
            <button className="btn-primary" onClick={() => setHoldingForm({ symbol: "", name: "", quantity: "", buy_price: "", current_price: "", asset_type: "equity" })} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Plus size={14} /> Add Holding
            </button>
          ) : (
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16, marginTop: 8 }}>
              <form onSubmit={addHolding}>
                <div className="form-grid-2">
                  <div className="form-field">
                    <label className="form-label">Symbol</label>
                    <input required placeholder="e.g. RELIANCE" value={holdingForm.symbol}
                      onChange={e => setHoldingForm({ ...holdingForm, symbol: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Name</label>
                    <input required placeholder="e.g. Reliance Industries" value={holdingForm.name}
                      onChange={e => setHoldingForm({ ...holdingForm, name: e.target.value })} />
                  </div>
                </div>
                <div className="form-grid-2">
                  <div className="form-field">
                    <label className="form-label">Quantity</label>
                    <input type="number" required step="0.0001" placeholder="10" value={holdingForm.quantity}
                      onChange={e => setHoldingForm({ ...holdingForm, quantity: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Buy Price (₹)</label>
                    <input type="number" required step="0.01" placeholder="2500" value={holdingForm.buy_price}
                      onChange={e => setHoldingForm({ ...holdingForm, buy_price: e.target.value })} />
                  </div>
                </div>
                <div className="form-grid-2">
                  <div className="form-field">
                    <label className="form-label">Current Price (₹)</label>
                    <input type="number" step="0.01" placeholder="2800" value={holdingForm.current_price}
                      onChange={e => setHoldingForm({ ...holdingForm, current_price: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Type</label>
                    <select value={holdingForm.asset_type} onChange={e => setHoldingForm({ ...holdingForm, asset_type: e.target.value })}>
                      <option value="equity">Equity</option><option value="mf">Mutual Fund</option>
                      <option value="etf">ETF</option><option value="crypto">Crypto</option>
                      <option value="fd">FD</option><option value="gold">Gold</option>
                    </select>
                  </div>
                </div>
                <div className="form-actions">
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Adding…" : "Add"}</button>
                  <button type="button" className="btn-secondary" onClick={() => setHoldingForm(null)}>Cancel</button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
