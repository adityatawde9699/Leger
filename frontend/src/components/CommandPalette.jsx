import React from "react";
import { Search, ArrowRight, Plus, Target, BarChart3, Sparkles, LayoutDashboard, Download, Shield, Globe, Receipt, Wallet, Briefcase, Gauge, Banknote } from "lucide-react";

const ACTIONS = [
  { id: "add-expense", label: "Add expense", desc: "Log a new expense transaction", view: "transactions", Icon: Plus },
  { id: "add-income", label: "Add income", desc: "Log new income", view: "transactions", Icon: Plus },
  { id: "import-sms", label: "Import SMS messages", desc: "Parse UPI SMS", view: "transactions", Icon: Plus },
  { id: "import-statement", label: "Upload bank statement", desc: "Import CSV, spreadsheet, or PDF", view: "transactions", Icon: Plus },
  { id: "view-dashboard", label: "Go to Dashboard", desc: "Financial overview", view: "dashboard", Icon: LayoutDashboard },
  { id: "view-budgets", label: "Goals & Budgets", desc: "Manage spending limits", view: "budgets", Icon: Target },
  { id: "view-analytics", label: "Analytics", desc: "Spending trends & patterns", view: "analytics", Icon: BarChart3 },
  { id: "ask-ai", label: "Ask Amadeus AI", desc: "Get financial advice", view: "advisor", Icon: Sparkles },
  { id: "scan-receipt", label: "Scan receipt", desc: "Extract data from receipt image", view: "transactions", Icon: Receipt },
  { id: "recategorize", label: "Re-categorize transactions", desc: "Use AI to fix 'Other' categories", view: "transactions", Icon: Sparkles },
  { id: "manage-accounts", label: "Manage accounts", desc: "Add or edit bank accounts", view: "accounts", Icon: Wallet },
  { id: "export-csv", label: "Export as CSV", desc: "Download transactions spreadsheet", view: "export", Icon: Download },
  { id: "export-tally", label: "Export for Tally", desc: "Tally Prime / ERP 9 XML", view: "export", Icon: Download },
  { id: "gst-report", label: "GST Report", desc: "View GST slab breakdown", view: "export", Icon: Receipt },
  { id: "audit-log", label: "View audit log", desc: "Activity history & compliance", view: "audit", Icon: Shield },
  { id: "webhooks", label: "Manage webhooks", desc: "Register event integrations", view: "audit", Icon: Globe },
  { id: "investments", label: "Investments", desc: "Track portfolios & holdings", view: "investments", Icon: Briefcase },
  { id: "financial-picture", label: "Financial picture", desc: "Review your recorded cash flow and data gaps", view: "credit", Icon: Gauge },
  { id: "benchmarks", label: "Peer comparison status", desc: "See why peer rankings are unavailable", view: "credit", Icon: BarChart3 },
  { id: "bill-negotiate", label: "Negotiate bills", desc: "AI strategies to reduce costs", view: "advisor", Icon: Banknote },
];

export default function CommandPalette({ open, onClose, onNavigate }) {
  const [query, setQuery] = React.useState("");
  const [selected, setSelected] = React.useState(0);
  const inputRef = React.useRef(null);
  const paletteRef = React.useRef(null);
  const previousFocusRef = React.useRef(null);

  React.useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement;
      setQuery("");
      setSelected(0);
      const focusTimer = setTimeout(() => inputRef.current?.focus(), 50);
      return () => { clearTimeout(focusTimer); previousFocusRef.current?.focus?.(); };
    }
    return undefined;
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
    if (e.key === "Tab") {
      const focusable = [...(paletteRef.current?.querySelectorAll("input, button:not([disabled])") || [])];
      if (focusable.length) {
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelected((s) => Math.min(s + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter" && document.activeElement === inputRef.current && filtered[selected]) {
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
      <div ref={paletteRef} className="cmd-palette" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={handleKeyDown}>
        <div className="cmd-header">
          <Search size={16} className="cmd-search-icon" />
          <input
            ref={inputRef}
            className="cmd-input"
            placeholder="Type a command or search…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(0); }}
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
