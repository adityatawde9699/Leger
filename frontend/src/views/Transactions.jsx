import React from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, KEYS, money, today, EXPENSE_CATEGORIES, INCOME_CATEGORIES, CATEGORY_COLORS } from "../lib";
import { useToast } from "../components/ui";
import {
  Trash2, Upload, Search, FileText, MessageSquare, PlusCircle,
  CheckSquare, Camera, AlertTriangle, Tag, X, CheckCircle,
} from "lucide-react";

const PAGE       = 50;
const UNDO_DELAY = 5000;

const ALL_CATEGORIES = [...EXPENSE_CATEGORIES, "Salary", "Freelance"];

function ConfidenceBadge({ confidence }) {
  if (confidence == null) return null;
  const pct = Math.round(confidence * 100);
  const [color, bg] =
    confidence >= 0.8 ? ["var(--positive)", "var(--positive-soft)"] :
    confidence >= 0.6 ? ["var(--warning)", "rgba(250,204,21,0.12)"] :
                        ["var(--negative)", "var(--negative-soft)"];
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 8,
      color, background: bg, border: `1px solid ${color}30`,
    }} title={`Categorization confidence: ${pct}%`}>
      {pct}%
    </span>
  );
}

function RecategorizeDropdown({ tx, onSave }) {
  const [open, setOpen]         = React.useState(false);
  const [saving, setSaving]     = React.useState(false);
  const [selected, setSelected] = React.useState(tx.category);
  const ref = React.useRef(null);

  React.useEffect(() => {
    if (!open) return;
    function close(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const save = async (cat) => {
    setSaving(true);
    try {
      await apiFetch(`/transactions/${tx.id}/correct-category`, {
        method: "POST",
        body: JSON.stringify({ category: cat }),
      });
      onSave(tx.id, cat);
      setOpen(false);
    } finally { setSaving(false); }
  };

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        title="Re-categorize" style={{
          background: "none", border: "1px solid var(--border)", borderRadius: 6,
          padding: "3px 8px", fontSize: 11, cursor: "pointer", color: "var(--text-muted)",
          display: "flex", alignItems: "center", gap: 4,
        }}>
        <Tag size={10} /> {saving ? "…" : "Fix"}
      </button>
      {open && (
        <div style={{
          position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 200,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12,
          boxShadow: "0 8px 32px rgba(0,0,0,0.15)", minWidth: 180, maxHeight: 280,
          overflowY: "auto",
        }}>
          <div style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, borderBottom: "1px solid var(--border)" }}>
            Correct Category
          </div>
          {ALL_CATEGORIES.map(cat => (
            <button key={cat} onClick={() => save(cat)}
              style={{
                display: "block", width: "100%", textAlign: "left", padding: "8px 14px",
                background: cat === tx.category ? "var(--positive-soft)" : "none",
                border: "none", fontSize: 13, cursor: "pointer", color: "var(--text-primary)",
                fontWeight: cat === tx.category ? 700 : 400,
              }}
              onMouseEnter={e => e.currentTarget.style.background = "var(--surface-secondary)"}
              onMouseLeave={e => e.currentTarget.style.background = cat === tx.category ? "var(--positive-soft)" : "none"}
            >
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: CATEGORY_COLORS[cat] || "var(--text-secondary)", marginRight: 8 }} />
              {cat}
              {cat === tx.category && <CheckCircle size={11} style={{ marginLeft: 6, color: "var(--primary)", verticalAlign: "middle" }} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ReceiptUploadModal({ onClose, onImport, toast }) {
  const [file,      setFile]      = React.useState(null);
  const [preview,   setPreview]   = React.useState(null);
  const [scanning,  setScanning]  = React.useState(false);
  const [result,    setResult]    = React.useState(null);

  const handleFile = (f) => {
    setFile(f);
    setResult(null);
    const reader = new FileReader();
    reader.onload = e => setPreview(e.target.result);
    reader.readAsDataURL(f);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith("image/")) handleFile(f);
  };

  const scan = async () => {
    if (!file) return;
    setScanning(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const data = await apiFetch("/receipts/scan", { method: "POST", body });
      setResult(data);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setScanning(false);
    }
  };

  const addFromReceipt = async () => {
    if (!result) return;
    setScanning(true);
    try {
      await apiFetch("/transactions", {
        method: "POST",
        body: JSON.stringify({
          type:        "expense",
          amount:      Number(result.amount),
          category:    result.category,
          description: result.description,
          date:        result.date,
          source:      "receipt",
        }),
      });
      toast("Receipt transaction added!", "success");
      onImport();
      onClose();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setScanning(false);
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
    }} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: "var(--surface)", borderRadius: 20, padding: 28,
        width: "100%", maxWidth: 480, boxShadow: "0 24px 80px rgba(0,0,0,0.25)",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 17, fontWeight: 800, color: "var(--text-primary)" }}>
              📷 Scan Receipt
            </div>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
              AI will extract transaction details automatically
            </div>
          </div>
          <button onClick={onClose}
            style={{ background: "var(--surface-secondary)", border: "none", borderRadius: 8, padding: 8, cursor: "pointer" }}>
            <X size={16} style={{ color: "var(--text-muted)" }} />
          </button>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => document.getElementById("receipt-input").click()}
          style={{
            border: `2px dashed ${preview ? "var(--primary)" : "var(--border)"}`,
            borderRadius: 16, padding: preview ? 0 : "36px 24px",
            textAlign: "center", cursor: "pointer",
            background: preview ? "transparent" : "var(--bg)",
            overflow: "hidden", minHeight: 160,
            transition: "border-color 0.2s",
          }}>
          {preview ? (
            <img src={preview} alt="Receipt" style={{ width: "100%", maxHeight: 260, objectFit: "contain", display: "block" }} />
          ) : (
            <>
              <Camera size={36} style={{ color: "var(--text-muted)", marginBottom: 12 }} />
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
                Drop receipt image here
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                or click to browse · JPG, PNG, WEBP
              </div>
            </>
          )}
          <input id="receipt-input" type="file" accept="image/*"
            style={{ display: "none" }}
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
        </div>

        {/* Scan result */}
        {result && (
          <div style={{
            marginTop: 16, padding: "14px 16px", borderRadius: 12,
            background: "var(--positive-soft)", border: "1px solid var(--primary)",
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 10 }}>
              ✅ Receipt Scanned
              {result.confidence != null && (
                <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginLeft: 8 }}>
                  ({Math.round(result.confidence * 100)}% confidence)
                </span>
              )}
            </div>
            {[
              ["Description", result.description],
              ["Amount",      `₹${Number(result.amount).toLocaleString("en-IN")}`],
              ["Category",    result.category],
              ["Date",        result.date],
            ].map(([k, v]) => (
              <div key={k} style={{ display: "flex", gap: 8, fontSize: 13, marginBottom: 4 }}>
                <span style={{ color: "var(--text-muted)", minWidth: 90 }}>{k}:</span>
                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{v}</span>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          {!result ? (
            <button className="btn-primary" onClick={scan}
              disabled={!file || scanning}
              style={{ flex: 1, padding: "12px 0" }}>
              {scanning ? "Scanning…" : "🔍 Scan Receipt"}
            </button>
          ) : (
            <button className="btn-primary" onClick={addFromReceipt}
              disabled={scanning}
              style={{ flex: 1, padding: "12px 0" }}>
              {scanning ? "Adding…" : "✓ Add Transaction"}
            </button>
          )}
          {result && (
            <button className="btn-secondary" onClick={() => { setResult(null); setFile(null); setPreview(null); }}
              style={{ padding: "12px 18px" }}>
              Rescan
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Transactions() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [submitting,   setSubmitting]   = React.useState(false);
  const [importing,    setImporting]    = React.useState(false);
  const [search,       setSearch]       = React.useState("");
  const [filterCat,    setFilterCat]    = React.useState("");
  const [filterType,   setFilterType]   = React.useState("");
  const [smsText,      setSmsText]      = React.useState("");
  const [importStatus, setImportStatus] = React.useState(null);
  const [activeTab,    setActiveTab]    = React.useState("manual");
  const [showReceipt,  setShowReceipt]  = React.useState(false);

  const [selectedIds,  setSelectedIds]  = React.useState(new Set());
  const [deletingIds,  setDeletingIds]  = React.useState(new Set());
  const [undoState,    setUndoState]    = React.useState(null);
  const undoCountRef = React.useRef(null);

  const [form, setForm] = React.useState({
    type: "expense", amount: "", category: "Groceries",
    description: "", date: today(), source: "cash",
  });

  const txQueryKey = KEYS.transactions({ search, category: filterCat, type: filterType });
  const txQuery = useInfiniteQuery({
    queryKey: txQueryKey,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: PAGE });
      if (search)     params.set("search",   search);
      if (filterCat)  params.set("category", filterCat);
      if (filterType) params.set("type",     filterType);
      if (pageParam)  params.set("cursor",   pageParam);
      return apiFetch(`/transactions?${params}`);
    },
    initialPageParam: null,
    getNextPageParam: (last) => (last.has_more ? last.next_cursor : undefined),
  });
  const transactions = React.useMemo(
    () => (txQuery.data?.pages || []).flatMap((p) => p.items),
    [txQuery.data]
  );
  const loading = txQuery.isLoading;
  const hasMore = txQuery.hasNextPage;

  // Anomalies flag unusual transactions; shares its cache entry with Dashboard/Analytics.
  const { data: anomaliesData } = useQuery({
    queryKey: KEYS.anomalies("3m"),
    queryFn: () => apiFetch("/analytics/anomalies?range=3m"),
  });
  const anomalyIds = React.useMemo(
    () => new Set((anomaliesData || []).map((a) => a.transaction_id)),
    [anomaliesData]
  );

  // Writes elsewhere (summary, anomalies, forecast, profile stats) are derived
  // from transaction history, so any mutation here busts all of them.
  function invalidateAfterWrite() {
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["summary"] });
    queryClient.invalidateQueries({ queryKey: KEYS.profileStats() });
    queryClient.invalidateQueries({ queryKey: ["anomalies"] });
    queryClient.invalidateQueries({ queryKey: KEYS.forecast() });
  }

  function patchTransactionInCache(id, patch) {
    queryClient.setQueryData(txQueryKey, (old) => old && {
      ...old,
      pages: old.pages.map((page) => ({
        ...page,
        items: page.items.map((t) => (t.id === id ? { ...t, ...patch } : t)),
      })),
    });
  }

  function removeTransactionsFromCache(ids) {
    const idSet = new Set(ids);
    queryClient.setQueryData(txQueryKey, (old) => old && {
      ...old,
      pages: old.pages.map((page) => ({
        ...page,
        items: page.items.filter((t) => !idSet.has(t.id)),
      })),
    });
  }

  const handleCategoryCorrection = (txId, newCat) => {
    patchTransactionInCache(txId, { category: newCat, confidence: 1.0 });
    toast(`Category updated to ${newCat}`, "success");
  };

  async function remove(id) {
    setDeletingIds((s) => new Set([...s, id]));
    await new Promise((r) => setTimeout(r, 280));
    const snapshot = queryClient.getQueryData(txQueryKey);
    removeTransactionsFromCache([id]);
    setDeletingIds((s) => { const n = new Set(s); n.delete(id); return n; });
    try {
      await apiFetch(`/transactions/${id}`, { method: "DELETE" });
      toast("Transaction deleted", "success");
      invalidateAfterWrite();
    } catch (e) {
      queryClient.setQueryData(txQueryKey, snapshot);
      toast(e.message, "error");
    }
  }

  function toggleSelect(id) {
    setSelectedIds((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function toggleSelectAll() {
    setSelectedIds(selectedIds.size === transactions.length ? new Set() : new Set(transactions.map(t => t.id)));
  }
  function clearSelection() { setSelectedIds(new Set()); }

  function requestBulkDelete() {
    if (selectedIds.size === 0) return;
    const ids = [...selectedIds];
    const snapshot = queryClient.getQueryData(txQueryKey);
    setDeletingIds(new Set(ids));
    setTimeout(() => { removeTransactionsFromCache(ids); setDeletingIds(new Set()); }, 300);
    setSelectedIds(new Set());
    let remaining = Math.ceil(UNDO_DELAY / 1000);
    const undoTimer = setTimeout(() => executeBulkDelete(ids), UNDO_DELAY);
    clearInterval(undoCountRef.current);
    undoCountRef.current = setInterval(() => {
      remaining -= 1;
      setUndoState(prev => prev ? { ...prev, countdown: remaining } : null);
      if (remaining <= 0) clearInterval(undoCountRef.current);
    }, 1000);
    setUndoState({ ids, snapshot, timer: undoTimer, countdown: remaining });
  }

  async function executeBulkDelete(ids) {
    clearInterval(undoCountRef.current); setUndoState(null);
    try {
      await apiFetch("/transactions/bulk-delete", { method: "POST", body: JSON.stringify({ transaction_ids: ids }) });
      toast(`${ids.length} transaction${ids.length > 1 ? "s" : ""} deleted`, "success");
      invalidateAfterWrite();
    } catch (e) {
      toast(e.message, "error");
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    }
  }

  function undoBulkDelete() {
    if (!undoState) return;
    clearTimeout(undoState.timer); clearInterval(undoCountRef.current);
    queryClient.setQueryData(txQueryKey, undoState.snapshot);
    setUndoState(null);
    toast("Deletion undone ✓", "success");
  }

  React.useEffect(() => () => { if (undoState?.timer) clearTimeout(undoState.timer); clearInterval(undoCountRef.current); }, [undoState]);

  async function addTransaction(e) {
    e.preventDefault();
    if (!form.amount || isNaN(Number(form.amount))) return toast("Enter a valid amount", "error");
    setSubmitting(true);
    try {
      await apiFetch("/transactions", { method: "POST", body: JSON.stringify({ ...form, amount: Number(form.amount) }) });
      setForm({ type: "expense", amount: "", category: "Groceries", description: "", date: today(), source: "cash" });
      invalidateAfterWrite();
      toast("Transaction added", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSubmitting(false); }
  }

  async function importSms() {
    const messages = smsText.split(/\n+/).map(l => l.trim()).filter(Boolean);
    if (!messages.length) return;
    setImporting(true);
    try {
      const saved = await apiFetch("/imports/sms", { method: "POST", body: JSON.stringify({ messages }) });
      setSmsText(""); invalidateAfterWrite();
      toast(`Imported ${saved.length} transactions from SMS`, "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setImporting(false); }
  }

  async function uploadStatement(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const body = new FormData(); body.append("file", file); e.target.value = "";
    try {
      const job = await apiFetch("/imports/statement", { method: "POST", body });
      setImportStatus("processing"); toast("Statement uploaded — processing…", "info");
      const poll = setInterval(async () => {
        try {
          const j = await apiFetch(`/imports/jobs/${job.id}`);
          setImportStatus(j.status);
          if (j.status === "done") { clearInterval(poll); toast(`Import complete — ${j.row_count} transactions added`, "success"); invalidateAfterWrite(); }
          else if (j.status === "failed") { clearInterval(poll); toast(`Import failed: ${j.error_message}`, "error"); }
        } catch { clearInterval(poll); }
      }, 1500);
    } catch (e) { toast(e.message, "error"); }
  }

  const TABS = [
    { id: "manual",    label: "Add Manually",   Icon: PlusCircle },
    { id: "receipt",   label: "Scan Receipt",   Icon: Camera },
    { id: "sms",       label: "SMS Import",     Icon: MessageSquare },
    { id: "statement", label: "Bank Statement", Icon: FileText },
  ];

  const allSelected  = transactions.length > 0 && selectedIds.size === transactions.length;
  const someSelected = selectedIds.size > 0 && !allSelected;

  return (
    <div className="view-transactions">
      <div>
        <h1 className="page-title">Transactions</h1>
        <p className="page-subtitle">Log, import and manage every transaction</p>
      </div>

      {/* Tabbed add/import card */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="import-tab-bar">
          {TABS.map(({ id, label, Icon }) => (
            <button key={id} onClick={() => { setActiveTab(id); if (id === "receipt") setShowReceipt(true); }}
              className={`import-tab-btn${activeTab === id ? " active" : ""}`}>
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>

        {/* Manual form */}
        {activeTab === "manual" && (
          <form onSubmit={addTransaction}>
            <div className="type-toggle">
              <button type="button" className={`type-btn${form.type === "expense" ? " active expense" : ""}`}
                onClick={() => setForm({ ...form, type: "expense", category: "Groceries" })}>Expense</button>
              <button type="button" className={`type-btn${form.type === "income" ? " active income" : ""}`}
                onClick={() => setForm({ ...form, type: "income", category: "Salary" })}>Income</button>
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
                <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
              </div>
            </div>
            <div className="form-field">
              <label className="form-label">Description</label>
              <input placeholder="What was this for?" value={form.description} required
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="form-field" style={{ marginBottom: 28 }}>
              <label className="form-label">Category</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {(form.type === "income" ? ["Salary", "Freelance", "Other"] : EXPENSE_CATEGORIES)
                  .map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <button type="submit" className="btn-primary" style={{ padding: "13px 28px" }} disabled={submitting}>
              {submitting ? "Adding…" : "Add Transaction"}
            </button>
          </form>
        )}

        {/* SMS import */}
        {activeTab === "sms" && (
          <div>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 20, lineHeight: 1.6 }}>
              Paste UPI / bank SMS messages (one per line). AI will extract transactions automatically.
            </p>
            <div className="form-field" style={{ marginBottom: 20 }}>
              <label className="form-label">SMS Messages</label>
              <textarea rows={6} placeholder="Paste SMS messages here, one per line…"
                value={smsText} onChange={(e) => setSmsText(e.target.value)} style={{ resize: "vertical" }} />
            </div>
            <button className="btn-primary" onClick={importSms} disabled={importing || !smsText.trim()}>
              <Upload size={16} /> {importing ? "Parsing…" : "Parse & Import SMS"}
            </button>
          </div>
        )}

        {/* Statement upload */}
        {activeTab === "statement" && (
          <div>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 20, lineHeight: 1.6 }}>
              Upload your bank statement in CSV, Excel, or PDF format. We'll automatically extract and categorize your transactions.
            </p>
            <div style={{ border: "2px dashed var(--border)", borderRadius: "var(--radius-sm)", padding: "40px 24px", textAlign: "center", marginBottom: 16, background: "var(--bg)" }}>
              <FileText size={32} style={{ color: "var(--text-muted)", marginBottom: 12 }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>Drop your file here</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 20 }}>Supports CSV, XLS, XLSX, PDF</div>
              <label className="btn-secondary" style={{ cursor: "pointer", padding: "10px 24px" }}>
                Browse File
                <input type="file" accept=".csv,.xls,.xlsx,.pdf" onChange={uploadStatement} style={{ display: "none" }} />
              </label>
            </div>
            {importStatus && (
              <div style={{
                padding: "14px 18px", borderRadius: 12, fontSize: 14, fontWeight: 600,
                background: importStatus === "done" ? "var(--positive-soft)" : importStatus === "failed" ? "var(--negative-soft)" : "rgba(56,189,248,0.12)",
                color: importStatus === "done" ? "var(--positive)" : importStatus === "failed" ? "var(--negative)" : "var(--info)",
                border: `1px solid ${importStatus === "done" ? "rgba(168,255,47,0.3)" : importStatus === "failed" ? "rgba(255,45,45,0.4)" : "rgba(56,189,248,0.3)"}`,
              }}>
                {importStatus === "processing" && "⏳ Processing your statement…"}
                {importStatus === "done"       && "✅ Import complete!"}
                {importStatus === "failed"     && "❌ Import failed. Please try again."}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Transaction list */}
      <div className="card">
        <div className="tx-list-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div className="chart-title">Recent Transactions</div>
            {selectedIds.size > 0 && (
              <span style={{ background: "var(--primary)", color: "white", fontSize: 12, fontWeight: 700, padding: "2px 10px", borderRadius: 99, lineHeight: 1.8 }}>
                {selectedIds.size} selected
              </span>
            )}
          </div>
          <div className="tx-filters">
            <div className="search-wrap" style={{ maxWidth: 280 }}>
              <Search size={15} className="search-icon" />
              <input className="search-input" placeholder="Search…"
                value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <select className="filter-select" value={filterCat}
              onChange={(e) => setFilterCat(e.target.value)} style={{ minWidth: 140 }}>
              <option value="">All Categories</option>
              {ALL_CATEGORIES.map(c => <option key={c}>{c}</option>)}
            </select>
            <select className="filter-select" value={filterType}
              onChange={(e) => setFilterType(e.target.value)} style={{ minWidth: 120 }}>
              <option value="">All Types</option>
              <option value="expense">Expense</option>
              <option value="income">Income</option>
            </select>
          </div>
        </div>

        {/* Desktop column headers */}
        <div className="tx-head">
          <div className="tx-checkbox-wrap">
            <input type="checkbox" className="tx-checkbox" checked={allSelected}
              ref={(el) => { if (el) el.indeterminate = someSelected; }}
              onChange={toggleSelectAll} aria-label="Select all transactions" />
          </div>
          <span>Date</span>
          <span>Category</span>
          <span>Description</span>
          <span>Confidence</span>
          <span>Amount</span>
          <span />
        </div>

        {/* Skeleton loading rows */}
        {loading && Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="tx-item">
            <div />
            {Array.from({ length: 5 }).map((_, j) => (
              <div key={j} className="skeleton" style={{ height: 14, borderRadius: 6 }} />
            ))}
            <div />
          </div>
        ))}

        {/* Error state */}
        {!loading && txQuery.isError && transactions.length === 0 && (
          <div style={{ textAlign: "center", padding: "56px 24px" }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
              Couldn't load transactions
            </div>
            <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 16 }}>{txQuery.error.message}</div>
            <button className="btn-secondary" onClick={() => txQuery.refetch()}>Retry</button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !txQuery.isError && transactions.length === 0 && (
          <div style={{ textAlign: "center", padding: "56px 24px" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>No transactions found</div>
            <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>Add one above or adjust your filters</div>
          </div>
        )}

        {/* Transaction rows */}
        {!loading && transactions.map((tx) => {
          const isSelected = selectedIds.has(tx.id);
          const isDeleting = deletingIds.has(tx.id);
          const isAnomaly  = anomalyIds.has(tx.id);
          return (
            <div key={tx.id}
              className={`tx-item${isSelected ? " selected" : ""}${isDeleting ? " tx-deleting" : ""}`}
              onClick={(e) => { if (e.target.closest("button") || e.target.closest(".tx-checkbox")) return; toggleSelect(tx.id); }}
              style={{ cursor: "pointer", borderLeft: isAnomaly ? "3px solid var(--warning)" : "3px solid transparent" }}
            >
              {/* Checkbox */}
              <div className="tx-checkbox-wrap" onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" className="tx-checkbox" checked={isSelected}
                  onChange={() => toggleSelect(tx.id)} aria-label={`Select ${tx.description}`} />
              </div>

              <span className="tx-date" style={{ color: "var(--text-secondary)", fontSize: 13, fontWeight: 500 }}>
                {tx.date}
                {isAnomaly && (
                  <span title="Anomaly detected" style={{ marginLeft: 4, verticalAlign: "middle" }}>
                    <AlertTriangle size={11} style={{ color: "var(--warning)" }} />
                  </span>
                )}
              </span>

              <span className="tx-cat-wrap" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: CATEGORY_COLORS[tx.category] || "var(--text-secondary)", flexShrink: 0 }} />
                <span style={{ color: "var(--text-secondary)", fontSize: 13, fontWeight: 500 }}>{tx.category}</span>
              </span>

              <span className="tx-desc" style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {tx.merchant_normalized || tx.description}
                {tx.merchant_normalized && tx.merchant_normalized !== tx.description && (
                  <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 6 }}>
                    {tx.description.length > 30 ? tx.description.slice(0, 30) + "…" : tx.description}
                  </span>
                )}
              </span>

              {/* Confidence badge */}
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <ConfidenceBadge confidence={tx.confidence} />
                <div onClick={(e) => e.stopPropagation()}>
                  <RecategorizeDropdown tx={tx} onSave={handleCategoryCorrection} />
                </div>
              </span>

              <span className={tx.type === "income" ? "tx-amount-income" : "tx-amount-expense"}>
                {tx.type === "income" ? "+" : "−"}{money(tx.amount)}
              </span>

              <button className="tx-delete-btn"
                onClick={(e) => { e.stopPropagation(); remove(tx.id); }}
                aria-label={`Delete ${tx.description}`} title="Delete">
                <Trash2 size={14} />
              </button>
            </div>
          );
        })}

        {/* Load more */}
        {hasMore && (
          <div style={{ padding: "16px 20px", borderTop: "1px solid var(--border)" }}>
            <button
              className="btn-secondary"
              onClick={() => txQuery.fetchNextPage()}
              disabled={txQuery.isFetchingNextPage}
              style={{ fontSize: 14 }}
            >
              {txQuery.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </div>

      {/* Receipt Upload Modal */}
      {showReceipt && (
        <ReceiptUploadModal
          onClose={() => { setShowReceipt(false); setActiveTab("manual"); }}
          onImport={invalidateAfterWrite}
          toast={toast}
        />
      )}

      {/* Floating bulk action bar */}
      {selectedIds.size > 0 && !undoState && (
        <div className="floating-action-bar">
          <CheckSquare size={18} style={{ color: "var(--primary)", flexShrink: 0 }} />
          <span>{selectedIds.size} transaction{selectedIds.size > 1 ? "s" : ""} selected</span>
          <button className="btn-clear-selection" onClick={clearSelection}>Clear</button>
          <button className="btn-delete-bulk" onClick={requestBulkDelete}>
            <Trash2 size={14} /> Delete {selectedIds.size > 1 ? `${selectedIds.size} transactions` : "transaction"}
          </button>
        </div>
      )}

      {/* Floating undo bar */}
      {undoState && (
        <div className="floating-undo-bar">
          <span style={{ color: "var(--text-secondary)" }}>
            🗑️ Deleting {undoState.ids.length} transaction{undoState.ids.length > 1 ? "s" : ""}…
          </span>
          <span style={{ fontSize: 13, fontWeight: 700, color: undoState.countdown <= 2 ? "var(--negative)" : "var(--text-muted)", minWidth: 20, textAlign: "center" }}>
            {undoState.countdown}s
          </span>
          <button className="btn-undo" onClick={undoBulkDelete}>Undo</button>
        </div>
      )}
    </div>
  );
}
