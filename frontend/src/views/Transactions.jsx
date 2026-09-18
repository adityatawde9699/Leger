import React from "react";
import { apiFetch, money, CATEGORY_COLORS, EXPENSE_CATEGORIES, INCOME_CATEGORIES } from "../lib";
import { Search, CheckSquare, Tag, X, Loader2 } from "lucide-react";
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
    currentGroup.sum += (tx.type === "income" ? Number(tx.amount) : -Number(tx.amount));
  }
  return groups;
}

export default function Transactions() {
  const toast = useToast();
  const [transactions, setTransactions] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [nextCursor, setNextCursor] = React.useState(null);
  const [hasMore, setHasMore] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [activeFilter, setActiveFilter] = React.useState("All");
  const [selectedIds, setSelectedIds] = React.useState(new Set());
  const [bulkUpdating, setBulkUpdating] = React.useState(false);
  const [showCategoryMenu, setShowCategoryMenu] = React.useState(false);

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
          amount: tx.amount, 
          category: newCategory, 
          description: tx.description, 
          date: tx.date, 
          source: tx.source 
        })
      })));
      toast(`Updated ${selectedIds.size} transactions`, "success");
      setSelectedIds(new Set());
      setShowCategoryMenu(false);
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
          {["All", "Expenses", "Income", "Recurring"].map(f => (
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
                      <div className="tx-merchant">
                        {tx.merchant_normalized || tx.description}
                        {tx.category === "Subscriptions" && <span className="tx-repeats-badge">REPEATS</span>}
                      </div>
                      <div className="tx-meta">
                        {tx.category} · {tx.source === "bank" ? "Everyday" : "Cash Wallet"}
                      </div>
                    </div>
                    
                    <div className={`tx-amount ${tx.type === "expense" ? "expense" : "income"}`}>
                      {tx.type === "expense" ? "−" : "+"}{money(tx.amount)}
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
