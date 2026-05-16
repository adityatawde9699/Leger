import React from "react";
import { Search, ArrowRight, Plus, Target, BarChart3, Sparkles, LayoutDashboard, Download, Shield, Globe, Receipt, Wallet, Briefcase, Gauge, Banknote } from "lucide-react";

const ACTIONS = [
  { id: "add-expense", label: "Add expense", desc: "Log a new expense transaction", view: "transactions", Icon: Plus },
  { id: "add-income", label: "Add income", desc: "Log new income", view: "transactions", Icon: Plus },
  { id: "import-sms", label: "Import SMS messages", desc: "Parse UPI SMS", view: "transactions", Icon: Plus },
  { id: "import-statement", label: "Upload bank statement", desc: "Import CSV or PDF", view: "transactions", Icon: Plus },
  { id: "view-dashboard", label: "Go to Dashboard", desc: "Financial overview", view: "dashboard", Icon: LayoutDashboard },
  { id: "view-budgets", label: "Goals & Budgets", desc: "Manage spending limits", view: "budgets", Icon: Target },
  { id: "view-analytics", label: "Analytics", desc: "Spending trends & patterns", view: "analytics", Icon: BarChart3 },
  { id: "ask-ai", label: "Ask AI Advisor", desc: "Get financial advice", view: "advisor", Icon: Sparkles },
  { id: "scan-receipt", label: "Scan receipt", desc: "Extract data from receipt image", view: "transactions", Icon: Receipt },
  { id: "recategorize", label: "Re-categorize transactions", desc: "Use AI to fix 'Other' categories", view: "transactions", Icon: Sparkles },
  { id: "manage-accounts", label: "Manage accounts", desc: "Add or edit bank accounts", view: "accounts", Icon: Wallet },
  { id: "export-csv", label: "Export as CSV", desc: "Download transactions spreadsheet", view: "export", Icon: Download },
  { id: "export-tally", label: "Export for Tally", desc: "Tally Prime / ERP 9 XML", view: "export", Icon: Download },
  { id: "gst-report", label: "GST Report", desc: "View GST slab breakdown", view: "export", Icon: Receipt },
  { id: "audit-log", label: "View audit log", desc: "Activity history & compliance", view: "audit", Icon: Shield },
  { id: "webhooks", label: "Manage webhooks", desc: "Register event integrations", view: "audit", Icon: Globe },
  { id: "investments", label: "Investments", desc: "Track portfolios & holdings", view: "investments", Icon: Briefcase },
  { id: "credit-score", label: "Credit Health Score", desc: "Financial health 300-900", view: "credit", Icon: Gauge },
  { id: "benchmarks", label: "Community Benchmarks", desc: "Compare spending to peers", view: "credit", Icon: BarChart3 },
  { id: "bill-negotiate", label: "Negotiate bills", desc: "AI strategies to reduce costs", view: "advisor", Icon: Banknote },
];

export default function CommandPalette({ open, onClose, onNavigate }) {
  const [query, setQuery] = React.useState("");
  const [selected, setSelected] = React.useState(0);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Global Cmd+K / Ctrl+K listener
  React.useEffect(() => {
    function handler(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (open) onClose();
        else onClose("toggle");
      }
      if (e.key === "Escape" && open) onClose();
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  const filtered = React.useMemo(() => {
    if (!query.trim()) return ACTIONS;
    const q = query.toLowerCase();
    return ACTIONS.filter(
      (a) => a.label.toLowerCase().includes(q) || a.desc.toLowerCase().includes(q)
    );
  }, [query]);

  function handleKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter" && filtered[selected]) {
      e.preventDefault();
      execute(filtered[selected]);
    }
  }

  function execute(action) {
    onNavigate(action.view);
    onClose();
  }

  if (!open) return null;

  return (
    <>
      <div className="cmd-backdrop" onClick={onClose} />
      <div className="cmd-palette" role="dialog" aria-label="Command palette">
        <div className="cmd-header">
          <Search size={16} className="cmd-search-icon" />
          <input
            ref={inputRef}
            className="cmd-input"
            placeholder="Type a command or search…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(0); }}
            onKeyDown={handleKeyDown}
            aria-label="Search commands"
          />
          <kbd className="cmd-kbd">ESC</kbd>
        </div>
        <div className="cmd-list">
          {filtered.length === 0 && (
            <div className="cmd-empty">No matching commands</div>
          )}
          {filtered.map((action, i) => (
            <button
              key={action.id}
              className={`cmd-item${i === selected ? " selected" : ""}`}
              onClick={() => execute(action)}
              onMouseEnter={() => setSelected(i)}
            >
              <action.Icon size={16} className="cmd-item-icon" />
              <div className="cmd-item-text">
                <span className="cmd-item-label">{action.label}</span>
                <span className="cmd-item-desc">{action.desc}</span>
              </div>
              <ArrowRight size={14} className="cmd-item-arrow" />
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
