import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, money, KEYS } from "../lib";
import { useToast } from "../components/ui";
import {
  Briefcase, TrendingUp, TrendingDown, Plus, Trash2,
  BarChart3, PiggyBank, Bitcoin, Landmark, Award, Activity, Zap,
} from "lucide-react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
} from "recharts";


const TYPE_META = {
  stocks:       { Icon: BarChart3,  color: "var(--info)", bg: "rgba(56,189,248,0.12)",  label: "Stocks" },
  mutual_funds: { Icon: PiggyBank,  color: "var(--positive)", bg: "var(--positive-soft)",  label: "Mutual Funds" },
  crypto:       { Icon: Bitcoin,    color: "var(--warning)", bg: "rgba(250,204,21,0.12)",  label: "Crypto" },
  fixed_deposit:{ Icon: Landmark,   color: "var(--info)", bg: "rgba(56,189,248,0.12)",  label: "Fixed Deposit" },
  gold:         { Icon: Award,      color: "var(--warning)", bg: "rgba(250,204,21,0.12)",  label: "Gold" },
};

export default function Investments() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [showForm,    setShowForm]    = React.useState(false);
  const [form,        setForm]        = React.useState({ name: "", portfolio_type: "stocks" });
  const [selected,    setSelected]    = React.useState(null);
  const [holdingForm, setHoldingForm] = React.useState(null);
  const [saving,      setSaving]      = React.useState(false);

  const portfoliosQuery = useQuery({ queryKey: KEYS.portfolios(), queryFn: () => apiFetch("/portfolios") });
  const { data: summary } = useQuery({ queryKey: KEYS.portfolioSummary(), queryFn: () => apiFetch("/portfolios/summary") });
  const { data: analytics } = useQuery({ queryKey: KEYS.portfolioAnalytics(), queryFn: () => apiFetch("/portfolios/analytics") });
  const { data: holdingsData } = useQuery({
    queryKey: KEYS.holdings(selected?.id),
    queryFn: () => apiFetch(`/portfolios/${selected.id}/holdings`),
    enabled: !!selected,
  });

  const portfolios = portfoliosQuery.data || [];
  const loading = portfoliosQuery.isLoading;
  const holdings = holdingsData || [];

  function invalidatePortfolios() {
    queryClient.invalidateQueries({ queryKey: KEYS.portfolios() });
    queryClient.invalidateQueries({ queryKey: KEYS.portfolioSummary() });
    queryClient.invalidateQueries({ queryKey: KEYS.portfolioAnalytics() });
  }

  function selectPortfolio(p) {
    setSelected(p);
  }

  async function createPortfolio(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/portfolios", { method: "POST", body: JSON.stringify(form) });
      setForm({ name: "", portfolio_type: "stocks" });
      setShowForm(false);
      invalidatePortfolios();
      toast("Portfolio created", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  }

  async function deletePortfolio(id) {
    try {
      await apiFetch(`/portfolios/${id}`, { method: "DELETE" });
      if (selected?.id === id) setSelected(null);
      invalidatePortfolios();
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
          quantity:      Number(holdingForm.quantity),
          buy_price:     Number(holdingForm.buy_price),
          current_price: Number(holdingForm.current_price || 0),
        }),
      });
      setHoldingForm(null);
      queryClient.invalidateQueries({ queryKey: KEYS.holdings(selected.id) });
      invalidatePortfolios();
      toast("Holding added", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  }

  async function deleteHolding(id) {
    try {
      await apiFetch(`/holdings/${id}`, { method: "DELETE" });
      queryClient.invalidateQueries({ queryKey: KEYS.holdings(selected.id) });
      invalidatePortfolios();
      toast("Holding removed", "success");
    } catch (e) { toast(e.message, "error"); }
  }

  const pnlColor = (v) => v >= 0 ? "var(--positive)" : "var(--negative)";

  return (
    <div className="view-investments">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 32 }}>
        <div>
          <h1 className="page-title">Investments</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Track your portfolio, holdings, and returns</p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={16} /> New Portfolio
        </button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="account-grid" style={{ marginBottom: 24 }}>
          <div className="card hero-card" style={{ gridColumn: "span 2", padding: "32px" }}>
            <div className="hero-label"><Briefcase size={16} /> Total Invested</div>
            <div className="hero-amount">{money(summary.total_invested)}</div>
            <div className="hero-change muted" style={{ color: "var(--text-secondary)" }}>
              {summary.portfolio_count} portfolio{summary.portfolio_count !== 1 ? "s" : ""}
            </div>
          </div>
          <div className="card hero-card" style={{ gridColumn: "span 2", padding: "32px" }}>
            <div className="hero-label">
              {summary.total_pnl >= 0 ? <TrendingUp size={16} style={{ color: "var(--positive)" }} /> : <TrendingDown size={16} style={{ color: "var(--negative)" }} />}
              Current Value
            </div>
            <div className="hero-amount">{money(summary.total_current)}</div>
            <div className={`hero-change ${summary.total_pnl >= 0 ? "positive" : "negative"}`}>
              {summary.total_pnl >= 0 ? "+" : ""}{money(summary.total_pnl)} ({summary.total_pnl_pct}%)
            </div>
          </div>
        </div>
      )}

      {/* Portfolio Analytics */}
      {analytics && (analytics.allocation?.length > 0 || analytics.sharpe_ratio != null) && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            {/* Asset Allocation Donut */}
            {analytics.allocation?.length > 0 && (
              <div className="card" style={{ gridColumn: analytics.sharpe_ratio != null ? "1" : "1 / -1" }}>
                <div className="chart-card-header" style={{ marginBottom: 8 }}>
                  <div>
                    <div className="chart-title">Asset Allocation</div>
                    <div className="chart-subtitle">By investment type</div>
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={analytics.allocation} dataKey="value" innerRadius={55} outerRadius={82} paddingAngle={3} strokeWidth={0}>
                      {analytics.allocation.map((a, i) => {
                        const colors = ["var(--info)","var(--positive)","var(--warning)","var(--negative)","var(--info)"];
                        return <Cell key={a.asset_type} fill={colors[i % colors.length]} />;
                      })}
                    </Pie>
                    <Tooltip
                      formatter={(val, name) => [money(val), name]}
                      contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}
                    />
                    <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
                  {analytics.allocation.map((a) => (
                    <div key={a.asset_type} style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>
                      {a.asset_type}: {a.pct?.toFixed(1)}%
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Analytics KPIs */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                {
                  label: "Total Return",
                  val: analytics.total_return_pct != null ? `${analytics.total_return_pct > 0 ? "+" : ""}${analytics.total_return_pct?.toFixed(1)}%` : "—",
                  sub: "vs invested capital",
                  color: analytics.total_return_pct >= 0 ? "var(--positive)" : "var(--negative)",
                  Icon: TrendingUp,
                },
                {
                  label: "Sharpe Ratio",
                  val: analytics.sharpe_ratio != null ? analytics.sharpe_ratio.toFixed(2) : "—",
                  sub: analytics.sharpe_ratio >= 1 ? "Excellent risk-adjusted return" : analytics.sharpe_ratio >= 0 ? "Acceptable" : "Below risk-free rate",
                  color: "var(--info)",
                  Icon: Activity,
                },
                {
                  label: "XIRR",
                  val: analytics.xirr != null ? `${(analytics.xirr * 100).toFixed(1)}%` : "—",
                  sub: "Annualized IRR",
                  color: "var(--warning)",
                  Icon: Zap,
                },
                {
                  label: "Max Drawdown",
                  val: analytics.max_drawdown_pct != null ? `${analytics.max_drawdown_pct.toFixed(1)}%` : "—",
                  sub: "Peak-to-trough loss",
                  color: "var(--negative)",
                  Icon: TrendingDown,
                },
              ].map(({ label, val, sub, color, Icon }) => (
                <div key={label} className="card" style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}18`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Icon size={18} style={{ color }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", marginBottom: 1 }}>{label}</div>
                    <div style={{ fontSize: 20, fontWeight: 800, color }}>{val}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{sub}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Best / Worst performers */}
          {(analytics.best_performer || analytics.worst_performer) && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              {analytics.best_performer && (
                <div className="card" style={{ padding: "14px 18px", borderLeft: "3px solid var(--positive)" }}>
                  <div style={{ fontSize: 11, color: "var(--positive)", fontWeight: 700, marginBottom: 4 }}>🏆 Best Performer</div>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>{analytics.best_performer.symbol}</div>
                  <div style={{ fontSize: 13, color: "var(--positive)", fontWeight: 600 }}>+{analytics.best_performer.return_pct?.toFixed(1)}% return</div>
                </div>
              )}
              {analytics.worst_performer && (
                <div className="card" style={{ padding: "14px 18px", borderLeft: "3px solid var(--negative)" }}>
                  <div style={{ fontSize: 11, color: "var(--negative)", fontWeight: 700, marginBottom: 4 }}>📉 Worst Performer</div>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>{analytics.worst_performer.symbol}</div>
                  <div style={{ fontSize: 13, color: "var(--negative)", fontWeight: 600 }}>{analytics.worst_performer.return_pct?.toFixed(1)}% return</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Portfolio grid */}
      <div className="portfolio-grid" style={{ marginBottom: 24 }}>
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div className="card" key={i} style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 24 }}>
              <div className="skeleton" style={{ height: 14, width: '60%', borderRadius: 6 }} />
              <div className="skeleton" style={{ height: 28, width: '80%', borderRadius: 6 }} />
            </div>
          ))
        ) : portfolios.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', padding: '48px 24px', gridColumn: '1 / -1' }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>No portfolios yet</div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>Create your first portfolio to track investments</div>
          </div>
        ) : (
          portfolios.map(p => {
            const meta = TYPE_META[p.portfolio_type] || TYPE_META.stocks;
            const IconComp = meta.Icon;
            return (
              <button
                key={p.id}
                className={`card portfolio-card${selected?.id === p.id ? " selected" : ""}`}
                onClick={() => selectPortfolio(p)}
                style={{ borderTop: `3px solid ${meta.color}`, textAlign: 'left' }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{ width: 44, height: 44, borderRadius: 12, background: meta.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', color: meta.color, flexShrink: 0 }}>
                      <IconComp size={22} />
                    </div>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{p.name}</div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: meta.color, marginTop: 2 }}>{meta.label}</div>
                    </div>
                  </div>
                  <button className="tx-delete-btn" onClick={(e) => { e.stopPropagation(); deletePortfolio(p.id); }}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </button>
            );
          })
        )}
      </div>

      {/* Create form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 24 }}>
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
            <div style={{ display: 'flex', gap: 12 }}>
              <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Creating…" : "Create Portfolio"}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Holdings */}
      {selected && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
            <div className="chart-title">{selected.name} — Holdings</div>
            {!holdingForm && (
              <button className="btn-primary" style={{ fontSize: 14, padding: '8px 16px' }}
                onClick={() => setHoldingForm({ symbol: "", name: "", quantity: "", buy_price: "", current_price: "", asset_type: "equity" })}>
                <Plus size={14} /> Add Holding
              </button>
            )}
          </div>

          {holdings.length === 0 && !holdingForm ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📈</div>
              <div style={{ fontWeight: 600 }}>No holdings yet</div>
            </div>
          ) : (
            <>
              {/* Desktop Table Layout */}
              <div className="holdings-table" style={{ overflowX: 'auto', marginBottom: holdingForm ? 24 : 0 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ background: 'var(--bg)', borderRadius: 8 }}>
                      {['Symbol', 'Name', 'Qty', 'Buy Price', 'Current', 'P&L', ''].map(h => (
                        <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {holdings.map(h => {
                      const pnl    = (Number(h.current_price) - Number(h.buy_price)) * Number(h.quantity);
                      const pnlPct = Number(h.buy_price) > 0 ? ((Number(h.current_price) - Number(h.buy_price)) / Number(h.buy_price) * 100).toFixed(1) : 0;
                      return (
                        <tr key={h.id} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '14px 16px', fontWeight: 700 }}>{h.symbol}</td>
                          <td style={{ padding: '14px 16px', color: 'var(--text-secondary)' }}>{h.name}</td>
                          <td style={{ padding: '14px 16px' }}>{Number(h.quantity)}</td>
                          <td style={{ padding: '14px 16px' }}>{money(h.buy_price)}</td>
                          <td style={{ padding: '14px 16px', fontWeight: 600 }}>{money(h.current_price)}</td>
                          <td style={{ padding: '14px 16px', color: pnlColor(pnl), fontWeight: 700 }}>
                            <span style={{ background: pnl >= 0 ? 'var(--positive-soft)' : 'var(--negative-soft)', padding: '4px 10px', borderRadius: 8 }}>
                              {pnl >= 0 ? "+" : ""}{money(pnl)} ({pnlPct}%)
                            </span>
                          </td>
                          <td style={{ padding: '14px 16px' }}>
                            <button className="tx-delete-btn" onClick={() => deleteHolding(h.id)}><Trash2 size={13} /></button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Mobile Card Layout */}
              <div className="holdings-mobile-list" style={{ marginBottom: holdingForm ? 24 : 0 }}>
                {holdings.map(h => {
                  const pnl    = (Number(h.current_price) - Number(h.buy_price)) * Number(h.quantity);
                  const pnlPct = Number(h.buy_price) > 0 ? ((Number(h.current_price) - Number(h.buy_price)) / Number(h.buy_price) * 100).toFixed(1) : 0;
                  return (
                    <div className="holding-mobile-card" key={h.id}>
                      <div className="holding-mobile-row-1">
                        <div>
                          <div className="holding-mobile-symbol">{h.symbol}</div>
                          <div className="holding-mobile-name">{h.name}</div>
                        </div>
                        <button className="tx-delete-btn" onClick={() => deleteHolding(h.id)} aria-label={`Delete ${h.symbol}`}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                      
                      <div className="holding-mobile-grid">
                        <div>
                          <div className="holding-mobile-label">Quantity</div>
                          <div className="holding-mobile-value">{Number(h.quantity)}</div>
                        </div>
                        <div>
                          <div className="holding-mobile-label">Buy Price</div>
                          <div className="holding-mobile-value">{money(h.buy_price)}</div>
                        </div>
                        <div>
                          <div className="holding-mobile-label">Current</div>
                          <div className="holding-mobile-value">{money(h.current_price)}</div>
                        </div>
                        <div className="holding-mobile-pnl" style={{ color: pnlColor(pnl) }}>
                          <div className="holding-mobile-label">Total P&L</div>
                          <span style={{ background: pnl >= 0 ? 'var(--positive-soft)' : 'var(--negative-soft)', padding: '4px 10px', borderRadius: 8, fontSize: 13, fontWeight: 700 }}>
                            {pnl >= 0 ? "+" : ""}{money(pnl)} ({pnlPct}%)
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {holdingForm && (
            <div style={{ borderTop: holdings.length ? '1px solid var(--border)' : 'none', paddingTop: holdings.length ? 24 : 0 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 20 }}>New Holding</div>
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
                    <label className="form-label">Asset Type</label>
                    <select value={holdingForm.asset_type} onChange={e => setHoldingForm({ ...holdingForm, asset_type: e.target.value })}>
                      <option value="equity">Equity</option>
                      <option value="mf">Mutual Fund</option>
                      <option value="etf">ETF</option>
                      <option value="crypto">Crypto</option>
                      <option value="fd">FD</option>
                      <option value="gold">Gold</option>
                    </select>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 12 }}>
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Adding…" : "Add Holding"}</button>
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
