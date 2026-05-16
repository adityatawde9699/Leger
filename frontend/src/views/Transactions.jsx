import React from "react";
import { apiFetch, KEYS, money, today, EXPENSE_CATEGORIES, CATEGORY_COLORS } from "../lib";
import { useToast } from "../components/ui";
import { Trash2, Upload, Search, Filter } from "lucide-react";

const PAGE = 50;

export default function Transactions() {
  const toast = useToast();
  const [transactions, setTransactions] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [submitting, setSubmitting] = React.useState(false);
  const [importing, setImporting] = React.useState(false);
  const [nextCursor, setNextCursor] = React.useState(null);
  const [hasMore, setHasMore] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [filterCat, setFilterCat] = React.useState("");
  const [filterType, setFilterType] = React.useState("");
  const [smsText, setSmsText] = React.useState("");
  const [importJobId, setImportJobId] = React.useState(null);
  const [importStatus, setImportStatus] = React.useState(null);

  const [form, setForm] = React.useState({
    type: "expense", amount: "", category: "Groceries",
    description: "", date: today(), source: "cash",
  });

  // ── Load transactions ──────────────────────────────────────────────────────
  const loadTransactions = React.useCallback(async (reset = true) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: PAGE });
      if (search) params.set("search", search);
      if (filterCat) params.set("category", filterCat);
      if (filterType) params.set("type", filterType);
      if (!reset && nextCursor) params.set("cursor", nextCursor);
      const data = await apiFetch(`/transactions?${params}`);
      setTransactions((prev) => reset ? data.items : [...prev, ...data.items]);
      setNextCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [search, filterCat, filterType, nextCursor]);

  React.useEffect(() => { loadTransactions(true); }, [search, filterCat, filterType]);

  // ── Add transaction ────────────────────────────────────────────────────────
  async function addTransaction(e) {
    e.preventDefault();
    if (!form.amount || isNaN(Number(form.amount))) return toast("Enter a valid amount", "error");
    setSubmitting(true);
    try {
      await apiFetch("/transactions", {
        method: "POST",
        body: JSON.stringify({ ...form, amount: Number(form.amount) }),
      });
      setForm({ type: "expense", amount: "", category: "Groceries", description: "", date: today(), source: "cash" });
      await loadTransactions(true);
      toast("Transaction added", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  }

  // ── Delete with optimistic UI ──────────────────────────────────────────────
  async function remove(id) {
    const prev = [...transactions];
    setTransactions((t) => t.filter((x) => x.id !== id));
    try {
      await apiFetch(`/transactions/${id}`, { method: "DELETE" });
      toast("Deleted", "success");
    } catch (e) {
      setTransactions(prev);
      toast(e.message, "error");
    }
  }

  // ── SMS import ─────────────────────────────────────────────────────────────
  async function importSms() {
    const messages = smsText.split(/\n+/).map((l) => l.trim()).filter(Boolean);
    if (!messages.length) return;
    setImporting(true);
    try {
      const saved = await apiFetch("/imports/sms", {
        method: "POST",
        body: JSON.stringify({ messages }),
      });
      setSmsText("");
      await loadTransactions(true);
      toast(`Imported ${saved.length} transactions from SMS`, "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setImporting(false);
    }
  }

  // ── Statement upload with job polling ─────────────────────────────────────
  async function uploadStatement(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    e.target.value = "";
    try {
      const job = await apiFetch("/imports/statement", { method: "POST", body });
      setImportJobId(job.id);
      setImportStatus("processing");
      toast("Statement uploaded — processing…", "info");
      // Poll for completion
      const poll = setInterval(async () => {
        try {
          const j = await apiFetch(`/imports/jobs/${job.id}`);
          setImportStatus(j.status);
          if (j.status === "done") {
            clearInterval(poll);
            toast(`Import complete — ${j.row_count} transactions added`, "success");
            await loadTransactions(true);
          } else if (j.status === "failed") {
            clearInterval(poll);
            toast(`Import failed: ${j.error_message}`, "error");
          }
        } catch { clearInterval(poll); }
      }, 1500);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  return (
    <div className="view-transactions">
      <div className="page-title-block">
        <h1 className="page-title">Transactions</h1>
        <p className="page-subtitle">Log, import and manage every transaction</p>
      </div>

      {/* ── Add form ── */}
      <div className="card form-card">
        <div className="form-section-title">Add Transaction</div>
        <form onSubmit={addTransaction}>
          <div className="type-toggle">
            <button type="button"
              className={`type-btn${form.type === "expense" ? " active expense" : ""}`}
              onClick={() => setForm({ ...form, type: "expense", category: "Groceries" })}>
              Expense
            </button>
            <button type="button"
              className={`type-btn${form.type === "income" ? " active income" : ""}`}
              onClick={() => setForm({ ...form, type: "income", category: "Salary" })}>
              Income
            </button>
          </div>
          <div className="form-grid-2">
            <div className="form-field">
              <label className="form-label">Amount</label>
              <div className="input-prefix-wrap">
                <span className="input-prefix">₹</span>
                <input required type="number" min="1" step="0.01" placeholder="0.00"
                  value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
              </div>
            </div>
            <div className="form-field">
              <label className="form-label">Date</label>
              <input type="date" value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Description</label>
            <input placeholder="What was this for?" value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })} required />
          </div>
          <div className="form-field">
            <label className="form-label">Category</label>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {(form.type === "income" ? ["Salary","Freelance","Other"] : EXPENSE_CATEGORIES)
                .map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? "Adding…" : "Add Transaction"}
            </button>
          </div>
        </form>
      </div>

      {/* ── Import ── */}
      <div className="import-grid">
        <div className="card">
          <div className="form-section-title">SMS Import</div>
          <div className="form-field">
            <label className="form-label">Paste UPI SMS messages (one per line)</label>
            <textarea rows={4} placeholder="One message per line…"
              value={smsText} onChange={(e) => setSmsText(e.target.value)} />
          </div>
          <button className="btn-primary" onClick={importSms} disabled={importing || !smsText.trim()}>
            <Upload size={14} /> {importing ? "Parsing…" : "Parse SMS"}
          </button>
        </div>
        <div className="card">
          <div className="form-section-title">Statement Upload</div>
          <div className="form-field">
            <label className="form-label">Upload CSV or PDF bank statement</label>
            <input type="file" accept=".csv,.pdf" onChange={uploadStatement} />
          </div>
          {importStatus && (
            <div className={`import-status import-status-${importStatus}`}>
              {importStatus === "processing" && "⏳ Processing…"}
              {importStatus === "done" && "✅ Import complete"}
              {importStatus === "failed" && "❌ Import failed"}
            </div>
          )}
        </div>
      </div>

      {/* ── Search + Filter Bar ── */}
      <div className="card">
        <div className="filter-bar">
          <div className="search-wrap">
            <Search size={14} className="search-icon" />
            <input className="search-input" placeholder="Search transactions…"
              value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="filter-select" value={filterCat}
            onChange={(e) => setFilterCat(e.target.value)}>
            <option value="">All Categories</option>
            {EXPENSE_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select className="filter-select" value={filterType}
            onChange={(e) => setFilterType(e.target.value)}>
            <option value="">All Types</option>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
          </select>
        </div>

        <div className="tx-head">
          <span>Date</span><span>Category</span><span>Description</span><span>Amount</span><span />
        </div>

        {loading && Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="tx-item tx-skeleton">
            {Array.from({ length: 4 }).map((_, j) => (
              <div key={j} className="skeleton" style={{ height: 14, borderRadius: 4 }} />
            ))}
            <div />
          </div>
        ))}

        {!loading && transactions.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">📭</div>
            <div className="empty-state-title">No transactions found</div>
            <div className="empty-state-sub">Add one above or adjust your filters</div>
          </div>
        )}

        {!loading && transactions.map((tx) => (
          <div className="tx-item" key={tx.id}>
            <span>{tx.date}</span>
            <span style={{ color: CATEGORY_COLORS[tx.category] || "#9ca3af" }}>
              {tx.category}
            </span>
            <span>{tx.description}</span>
            <strong className={tx.type === "income" ? "tx-amount-income" : "tx-amount-expense"}>
              {tx.type === "income" ? "+" : "-"}{money(tx.amount)}
            </strong>
            <button className="tx-delete-btn" onClick={() => remove(tx.id)} aria-label={`Delete ${tx.description}`}>
              <Trash2 size={13} />
            </button>
          </div>
        ))}

        {hasMore && (
          <button className="btn-secondary" style={{ marginTop: 12 }}
            onClick={() => loadTransactions(false)}>
            Load more
          </button>
        )}
      </div>
    </div>
  );
}
