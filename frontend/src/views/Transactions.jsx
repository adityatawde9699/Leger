import React from "react";
import { apiFetch, money, CATEGORY_COLORS, EXPENSE_CATEGORIES, INCOME_CATEGORIES } from "../lib";
import { Search, CheckSquare, Tag, X, Loader2, Undo2 } from "lucide-react";
import { useToast } from "../components/ui";

const ALL_CATEGORIES = [...new Set([...EXPENSE_CATEGORIES, ...INCOME_CATEGORIES, "Subscriptions"])];

const PAGE = 50;

function formatGroupDate(dateStr) {
  const d = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  
  if (d.toDateString() === today.toDateString()) return "TODAY";
  if (d.toDateString() === yesterday.toDateString()) return "YESTERDAY";
  
  return d.toLocaleDateString("en-US", { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase();
}

function groupTransactions(txs) {
  const groups = [];
  let currentGroup = null;
  for (const tx of txs) {
    const key = formatGroupDate(tx.date);
    if (!currentGroup || currentGroup.label !== key) {
      currentGroup = { label: key, sum: 0, items: [] };
      groups.push(currentGroup);
    }
    currentGroup.items.push(tx);
    currentGroup.sum += ((tx.status || "posted") !== "posted" ? 0 : (["income", "refund", "reimbursement"].includes(tx.type) ? Number(tx.amount) : (["transfer"].includes(tx.type) ? 0 : -Number(tx.amount))));
  }
  return groups;
}

export default function Transactions({ initialFilter = "All" }) {
  const toast = useToast();
  const [transactions, setTransactions] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [nextCursor, setNextCursor] = React.useState(null);
  const [hasMore, setHasMore] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [activeFilter, setActiveFilter] = React.useState(initialFilter);
  const [selectedIds, setSelectedIds] = React.useState(new Set());
  const [bulkUpdating, setBulkUpdating] = React.useState(false);
  const [showCategoryMenu, setShowCategoryMenu] = React.useState(false);
  const [undoIds, setUndoIds] = React.useState([]);
  const [undoing, setUndoing] = React.useState(false);

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBulkRecategorize = async (newCategory) => {
    if (!selectedIds.size) return;
    setBulkUpdating(true);
    try {
      const txsToUpdate = transactions.filter(t => selectedIds.has(t.id));
      await Promise.all(txsToUpdate.map(tx => apiFetch(`/transactions/${tx.id}`, {
        method: "PUT",
        body: JSON.stringify({ 
          type: tx.type, 
          status: tx.status || "posted",
          amount: tx.amount, 
          category: newCategory, 
          description: tx.description, 
          date: tx.date, 
          source: tx.source,
          account_id: tx.account_id || null,
          running_balance: tx.running_balance || null,
        })
      })));
      toast(`Updated ${selectedIds.size} transactions`, "success");
      setUndoIds([...selectedIds]);
      setSelectedIds(new Set());
      setShowCategoryMenu(false);
      loadTransactions(true);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBulkUpdating(false);
    }
  };

  const handleBulkStatus = async (status) => {
    if (!selectedIds.size) return;
    setBulkUpdating(true);
    try {
      const txsToUpdate = transactions.filter(tx => selectedIds.has(tx.id));
      await Promise.all(txsToUpdate.map(tx => apiFetch(`/transactions/${tx.id}`, {
        method: "PUT",
        body: JSON.stringify({
          type: tx.type,
          status,
          amount: tx.amount,
          category: tx.category,
          description: tx.description,
          date: tx.date,
          source: tx.source,
          account_id: tx.account_id || null,
          running_balance: tx.running_balance || null,
        }),
      })));
      toast(status === "posted" ? "Transactions confirmed" : "Transactions excluded from totals", "success");
      setUndoIds([...selectedIds]);
      setSelectedIds(new Set());
      loadTransactions(true);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBulkUpdating(false);
    }
  };
  
  const loadTransactions = React.useCallback(async (reset = true) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: PAGE });
      if (search) params.set("search", search);
      if (activeFilter === "Expenses") params.set("type", "expense");
      if (activeFilter === "Income") params.set("type", "income");
      if (activeFilter === "Refunds") params.set("type", "refund");
      if (activeFilter === "Reimbursements") params.set("type", "reimbursement");
      if (activeFilter === "Transfers") params.set("type", "transfer");
      if (activeFilter === "Pending") params.set("status", "pending");
      if (activeFilter === "Excluded") params.set("status", "excluded");
      if (activeFilter === "Needs review") params.set("category", "Other");
      if (!reset && nextCursor) params.set("cursor", nextCursor);
      
      const data = await apiFetch(`/transactions?${params}`);
      let items = data.items;
      
      if (activeFilter === "Recurring") {
         items = items.filter(tx => tx.category === "Subscriptions");
      }
      
      setTransactions((prev) => reset ? items : [...prev, ...items]);
      setNextCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [search, activeFilter, nextCursor]);

  React.useEffect(() => { loadTransactions(true); }, [search, activeFilter]);

  const groups = groupTransactions(transactions);

  const undoLastBulkChange = async () => {
    if (!undoIds.length) return;
    setUndoing(true);
    try {
      await Promise.all(undoIds.map((id) => apiFetch(`/transactions/${id}/undo`, { method: "POST" })));
      toast(`Undid changes to ${undoIds.length} transaction${undoIds.length === 1 ? "" : "s"}`, "success");
      setUndoIds([]);
      loadTransactions(true);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setUndoing(false);
    }
  };

  return (
    <div className="view-transactions-activity">
      <div style={{ padding: "0 20px" }}>
        <h1 className="activity-title">Activity</h1>
        
        {/* Search */}
        <div className="activity-search">
          <Search size={18} color="var(--text-muted)" />
          <input 
            placeholder="Search merchants, notes, amounts" 
            value={search} 
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        
        {/* Filters */}
        <div className="activity-filters">
          {["All", "Expenses", "Income", "Refunds", "Reimbursements", "Transfers", "Pending", "Excluded", "Needs review", "Recurring"].map(f => (
            <button 
              key={f} 
              className={`filter-pill ${activeFilter === f ? "active" : ""}`}
              onClick={() => setActiveFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="activity-list">
        {loading && transactions.length === 0 && (
          <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
        )}
        
        {!loading && transactions.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No activity found.</div>
        )}
        
        {groups.map((group) => (
          <div key={group.label} className="tx-group">
            <div className="tx-group-header">
              <span>{group.label}</span>
              <span>{group.sum < 0 ? "−" : (group.sum > 0 ? "+" : "")}{money(Math.abs(group.sum))}</span>
            </div>
            
            <div className="tx-group-items">
              {group.items.map(tx => {
                const isSelected = selectedIds.has(tx.id);
                return (
                  <div 
                    key={tx.id} 
                    className={`activity-tx-card ${isSelected ? "selected" : ""}`}
                    onClick={() => toggleSelect(tx.id)}
                    style={{ cursor: "pointer", transition: "background 0.2s" }}
                  >
                    <div className="tx-checkbox-wrap" style={{ marginRight: 4 }}>
                      <input type="checkbox" className="tx-checkbox" checked={isSelected} readOnly />
                    </div>
                    
                    <div className="tx-icon-wrap" style={{ background: CATEGORY_COLORS[tx.category] || "var(--surface)" }}>
                      <div className="tx-icon-fallback">{tx.category.substring(0, 2).toUpperCase()}</div>
                    </div>
                    
                    <div className="tx-details">
                      <div className="tx-merchant" title={tx.merchant_normalized && tx.merchant_normalized !== tx.description ? tx.description : undefined}>
                        {tx.merchant_normalized || tx.description}
                        {tx.category === "Subscriptions" && <span className="tx-repeats-badge">REPEATS</span>}
                      </div>
                      {tx.merchant_normalized && tx.merchant_normalized !== tx.description && (
                        <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>Original: {tx.description}</div>
                      )}
                      <div className="tx-meta">
                        {tx.category} · {tx.source === "bank" ? "Everyday" : "Cash Wallet"} · {tx.status || "posted"}
                      </div>
                    </div>
                    
                    <div className={`tx-amount ${(tx.status || "posted") !== "posted" ? "muted" : (tx.type === "expense" ? "expense" : (tx.type === "transfer" ? "muted" : "income"))}`}>
                      {tx.type === "expense" ? "−" : (tx.type === "transfer" ? "↔" : "+")}{money(tx.amount)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        
        {hasMore && (
           <div style={{ padding: 20, textAlign: 'center' }}>
             <button className="btn-secondary" onClick={() => loadTransactions(false)}>Load more</button>
           </div>
        )}
      </div>

      {undoIds.length > 0 && selectedIds.size === 0 && (
        <div className="floating-undo-bar" role="status">
          <Undo2 size={17} style={{ color: "var(--primary)" }} />
          <span>Last bulk change applied to {undoIds.length} transaction{undoIds.length === 1 ? "" : "s"}</span>
          <button className="btn-undo" onClick={undoLastBulkChange} disabled={undoing}>
            {undoing ? "Undoing…" : "Undo"}
          </button>
          <button className="btn-clear-selection" onClick={() => setUndoIds([])} aria-label="Dismiss undo message"><X size={16} /></button>
        </div>
      )}

      {/* Floating bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="floating-action-bar" style={{ flexDirection: "column", alignItems: "stretch", padding: showCategoryMenu ? "16px" : "14px 22px" }}>
          {!showCategoryMenu ? (
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <CheckSquare size={18} style={{ color: "var(--primary)", flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{selectedIds.size} selected</span>
              <button className="btn-secondary" onClick={(e) => { e.stopPropagation(); setShowCategoryMenu(true); }} style={{ padding: "6px 14px", display: "flex", alignItems: "center", gap: 6 }}>
                <Tag size={14} /> Fix Category
              </button>
              <button className="btn-secondary" onClick={(e) => { e.stopPropagation(); handleBulkStatus("posted"); }} disabled={bulkUpdating} style={{ padding: "6px 14px" }}>
                Confirm
              </button>
              <button className="btn-secondary" onClick={(e) => { e.stopPropagation(); handleBulkStatus("excluded"); }} disabled={bulkUpdating} style={{ padding: "6px 14px" }}>
                Exclude
              </button>
              <button className="btn-clear-selection" onClick={(e) => { e.stopPropagation(); setSelectedIds(new Set()); }}>
                <X size={16} />
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontWeight: 600 }}>
                <span>Select new category</span>
                <button onClick={(e) => { e.stopPropagation(); setShowCategoryMenu(false); }} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={16} /></button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, maxHeight: "40vh", overflowY: "auto", paddingBottom: 8 }}>
                {ALL_CATEGORIES.map(c => (
                  <button key={c} className="category-pill" onClick={(e) => { e.stopPropagation(); handleBulkRecategorize(c); }} disabled={bulkUpdating}>
                    {c}
                  </button>
                ))}
              </div>
              {bulkUpdating && <div style={{ textAlign: "center", color: "var(--primary)", fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}><Loader2 size={14} className="spin" /> Updating...</div>}
            </div>
          )}
        </div>
      )}

      <div style={{ height: 100 }} /> {/* Padding for mobile nav */}
    </div>
  );
}
