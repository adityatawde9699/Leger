import React, { useState, useEffect, useRef, lazy, Suspense } from "react";
import { apiFetch, API_BASE, EXPENSE_CATEGORIES, setAuthToken, today } from "./lib";
import { clearGoogleSession, loadGoogleSession, silentlyRefreshGoogleSession, msUntilRefresh } from "./googleAuth";
import { useToast, LedgerLogo, CardSkeleton } from "./components/ui";
import Auth from "./views/Auth";
import CommandPalette from "./components/CommandPalette";

const Dashboard     = lazy(() => import("./views/Dashboard"));
const Transactions  = lazy(() => import("./views/Transactions"));
const Budgets       = lazy(() => import("./views/Budgets"));
const Goals         = lazy(() => import("./views/Goals"));
const Advisor       = lazy(() => import("./views/Advisor"));
const Accounts      = lazy(() => import("./views/Accounts"));
const ExportGST     = lazy(() => import("./views/ExportGST"));
const AuditWebhooks = lazy(() => import("./views/AuditWebhooks"));
const Investments   = lazy(() => import("./views/Investments"));
const CreditBenchmarks = lazy(() => import("./views/CreditBenchmarks"));
const Analytics     = lazy(() => import("./views/Analytics"));
const Profile       = lazy(() => import("./views/Profile"));

import {
  LayoutDashboard, Plus, Target, BarChart3, Sparkles,
  Wallet, Download, Shield, Briefcase, Gauge, LogOut,
  Loader2, X, Grid, User, Scan, Mic, Delete,
  FileText, MessageSquare, List
} from "lucide-react";

// Bottom-nav order: Home | Budgets | [ADD] | AI | More
const PRIMARY_VIEWS = [
  { id: "dashboard",    label: "Home",    Icon: LayoutDashboard },
  { id: "budgets",      label: "Budgets", Icon: Target },
  { id: "goals",        label: "Goals",   Icon: Target },
  { id: "advisor",      label: "AI",      Icon: Sparkles },
];

const SECONDARY_VIEWS = [
  { id: "transactions", label: "Activity",  Icon: List },
  { id: "investments",  label: "Investments",Icon: Briefcase },
  { id: "accounts",  label: "Accounts",     Icon: Wallet },
  { id: "analytics", label: "Analytics",    Icon: BarChart3 },
  { id: "credit",    label: "Credit Health", Icon: Gauge },
  { id: "export",    label: "Export & GST",  Icon: Download },
  { id: "audit",     label: "Audit Logs",    Icon: Shield },
];

const PAGE_TITLES = {
  dashboard:    "Dashboard",
  transactions: "Transactions",
  budgets:      "Budgets",
  goals:        "Goals",
  advisor:      "Amadeus AI",
  investments:  "Investments",
  accounts:     "Accounts",
  analytics:    "Analytics",
  credit:       "Credit Health",
  export:       "Export & GST",
  audit:        "Audit Logs",
  profile:      "Profile",
};

const ALL_VIEWS = [...PRIMARY_VIEWS, ...SECONDARY_VIEWS];

let _pingInterval = null;
function startKeepAlive() {
  if (_pingInterval) return;
  _pingInterval = setInterval(async () => {
    try { await fetch(`${API_BASE}/ping`); } catch { /* noop */ }
  }, 13 * 60 * 1000);
}
function stopKeepAlive() {
  if (_pingInterval) { clearInterval(_pingInterval); _pingInterval = null; }
}

function getInitials(displayName, email) {
  const name = displayName || email || "U";
  const parts = name.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

const AVATAR_GRADIENTS = [
  "linear-gradient(135deg, var(--primary), var(--info))",
  "linear-gradient(135deg, var(--info), var(--accent))",
  "linear-gradient(135deg, var(--primary), var(--warning))",
];
function pickGradient(str = "") {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_GRADIENTS[Math.abs(hash) % AVATAR_GRADIENTS.length];
}

function ViewFallback() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 16 }}>
      {[1,2,3].map(i => <CardSkeleton key={i} />)}
    </div>
  );
}

// Honor a `?view=` query param so PWA manifest shortcuts (and deep links)
// open the right screen. Falls back to the dashboard for unknown values.
function getInitialView() {
  const valid = new Set([...ALL_VIEWS.map((v) => v.id), "profile"]);
  const requested = new URLSearchParams(window.location.search).get("view");
  return requested && valid.has(requested) ? requested : "dashboard";
}

export default function App() {
  const toast = useToast();
  const [view, setView] = useState(getInitialView);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [moreDrawerOpen, setMoreDrawerOpen] = useState(false);
  const [session, setSession] = useState(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [profileData, setProfileData] = useState(null);

  // Swipe navigation state
  const [touchStart, setTouchStart] = useState(null);
  const [touchEnd, setTouchEnd] = useState(null);

  // Auth setup
  useEffect(() => {
    if (import.meta.env.VITE_AUTH_PROVIDER === "dev") {
      const saved = localStorage.getItem("dev-session");
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          setSession(parsed);
          setAuthToken(parsed.access_token);
        } catch { localStorage.removeItem("dev-session"); }
      }
      setLoadingAuth(false);
      return;
    }

    const googleSession = loadGoogleSession();
    setSession(googleSession);
    setAuthToken(googleSession?.access_token || null);
    setLoadingAuth(false);

    if (!googleSession) return undefined;

    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    let refreshTimer = null;

    // Schedules a silent re-auth attempt. On success the session is updated
    // transparently; only falls back to logout if Google cannot silently
    // re-authenticate (e.g. user has signed out of Google entirely).
    function scheduleRefresh(currentSession) {
      const delay = msUntilRefresh(currentSession);
      refreshTimer = window.setTimeout(async () => {
        try {
          const freshSession = await silentlyRefreshGoogleSession(clientId);
          setSession(freshSession);
          setAuthToken(freshSession.access_token);
          // Schedule the next refresh cycle for the new token.
          scheduleRefresh(freshSession);
        } catch {
          // Silent re-auth failed — user must log in manually.
          clearGoogleSession();
          setAuthToken(null);
          setSession(null);
        }
      }, delay);
    }

    scheduleRefresh(googleSession);
    return () => window.clearTimeout(refreshTimer);
  }, []);

  useEffect(() => {
    if (!session) return;
    apiFetch("/profile").then(p => setProfileData(p)).catch(() => {});
  }, [session]);

  useEffect(() => {
    if (session) startKeepAlive(); else stopKeepAlive();
  }, [session]);

  // Close more drawer on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") { setMoreDrawerOpen(false); setSheetOpen(false); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const handleSignOut = async () => {
    stopKeepAlive();
    if (import.meta.env.VITE_AUTH_PROVIDER === "dev") {
      localStorage.removeItem("dev-session"); setSession(null); setAuthToken(null); return;
    }
    clearGoogleSession();
    setSession(null);
    setAuthToken(null);
  };

  const renderView = () => {
    switch (view) {
      case "dashboard":    return <Dashboard userName={displayName} onNavigate={navigateTo} onAddTransaction={() => setSheetOpen(true)} />;
      case "transactions": return <Transactions />;
      case "budgets":      return <Budgets />;
      case "goals":        return <Goals />;
      case "analytics":    return <Analytics />;
      case "accounts":     return <Accounts />;
      case "investments":  return <Investments />;
      case "credit":       return <CreditBenchmarks />;
      case "export":       return <ExportGST />;
      case "audit":        return <AuditWebhooks />;
      case "advisor":      return <Advisor />;
      case "profile":      return <Profile onSignOut={handleSignOut} />;
      default:             return <Dashboard userName={displayName} onNavigate={navigateTo} onAddTransaction={() => setSheetOpen(true)} />;
    }
  };

  function navigateTo(id) {
    setView(id);
    setMoreDrawerOpen(false);
    setSheetOpen(false);
  }

  // Swipe handlers
  const onTouchStart = (e) => {
    setTouchEnd(null);
    setTouchStart(e.targetTouches[0].clientX);
  };

  const onTouchMove = (e) => {
    setTouchEnd(e.targetTouches[0].clientX);
  };

  const onTouchEndHandler = () => {
    if (!touchStart || !touchEnd) return;
    const distance = touchStart - touchEnd;
    const minSwipeDistance = 60;
    const isLeftSwipe = distance > minSwipeDistance;
    const isRightSwipe = distance < -minSwipeDistance;

    // Swipe only cycles through the 5 primary bottom-nav views for predictability
    if (isLeftSwipe || isRightSwipe) {
      const primaryIds = PRIMARY_VIEWS.map(v => v.id);
      const currentIndex = primaryIds.indexOf(view);
      if (currentIndex !== -1) {
        if (isLeftSwipe && currentIndex < primaryIds.length - 1) {
          navigateTo(primaryIds[currentIndex + 1]);
        }
        if (isRightSwipe && currentIndex > 0) {
          navigateTo(primaryIds[currentIndex - 1]);
        }
      }
    }
  };

  if (loadingAuth) {
    return (
      <div className="app-loading">
        <div className="app-loading-inner">
          <LedgerLogo size={64} />
          <Loader2 size={24} className="spin" style={{ color: "var(--primary)" }} />
        </div>
      </div>
    );
  }

  if (!session) return <Auth />;

  const initials = getInitials(profileData?.display_name, session?.user?.email || profileData?.email);
  const gradient = pickGradient(profileData?.id || session?.user?.id || "");
  const displayName = profileData?.display_name || session?.user?.email?.split("@")[0] || "User";
  const avatarUrl = profileData?.avatar_url;

  return (
    <div className="app">
      {/* ── Sidebar (Desktop only) ── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <LedgerLogo size={32} />
          <span className="sidebar-logo-name">Ledger</span>
        </div>

        <nav className="sidebar-nav">
          {ALL_VIEWS.map(({ id, label, Icon }) => (
            <button
              key={id}
              id={`sidebar-${id}`}
              className={`sidebar-item${view === id ? " active" : ""}`}
              onClick={() => navigateTo(id)}
              aria-current={view === id ? "page" : undefined}
            >
              <Icon size={18} aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button
            className={`sidebar-item${view === "profile" ? " active" : ""}`}
            onClick={() => navigateTo("profile")}
          >
            <div style={{
              width: 24, height: 24, borderRadius: 6,
              background: gradient, display: "flex",
              alignItems: "center", justifyContent: "center",
              fontSize: 10, color: "white", fontWeight: 700, flexShrink: 0,
              overflow: "hidden",
            }}>
              {avatarUrl ? <img src={avatarUrl} alt="Avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials}
            </div>
            Profile
          </button>
          <button
            className="sidebar-item"
            onClick={handleSignOut}
            style={{ color: "var(--negative)" }}
          >
            <LogOut size={18} />
            Sign Out
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div 
        className="main-wrapper"
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEndHandler}
      >
        {/* Mobile top header */}
        <header className="app-header glass">
          <div className="app-header-inner">
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <LedgerLogo size={28} />
              <span className="app-header-title">
                Ledger
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button
                className="header-icon-btn"
                onClick={() => setCmdOpen(true)}
                aria-label="Search"
                title="Search (Ctrl+K)"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              </button>
              <button
                onClick={() => navigateTo("profile")}
                style={{ border: "none", cursor: "pointer", background: "none", padding: 0 }}
                aria-label="Profile"
              >
                <div className={`header-avatar${view === "profile" ? " active" : ""}`}
                  style={{ background: gradient }}
                >
                  {avatarUrl ? <img src={avatarUrl} alt="Avatar" style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }} /> : initials}
                </div>
              </button>
            </div>
          </div>
        </header>

        <main className="page-content fade-in" id="main-content">
          <Suspense fallback={<ViewFallback />}>
            {renderView()}
          </Suspense>
        </main>
      </div>

      {/* ── Desktop FAB ── */}
      <button
        className="quick-add-fab"
        onClick={() => setSheetOpen(true)}
        aria-label="Add transaction"
        title="Add transaction (A)"
      >
        <Plus size={24} />
      </button>

      {/* ── Mobile Bottom Nav ── */}
      <nav className="mobile-bottom-nav glass" aria-label="Primary mobile navigation">
        {PRIMARY_VIEWS.slice(0, 2).map(({ id, label, Icon }) => {
          const isActive = view === id;
          return (
            <button
              key={id}
              id={`mob-nav-${id}`}
              className={`mobile-nav-item${isActive ? " active" : ""}`}
              onClick={() => navigateTo(id)}
              aria-label={label}
              aria-current={isActive ? "page" : undefined}
            >
              <div className="mob-icon-wrap">
                <Icon size={20} aria-hidden="true" />
                {isActive && <span className="mob-active-pip" />}
              </div>
              <span>{label}</span>
            </button>
          );
        })}

        {/* Center Add Button */}
        <button
          className="mobile-nav-item center-add-btn"
          onClick={() => setSheetOpen(true)}
          aria-label="Add"
        >
          <div className="center-add-icon-wrap">
            <Plus size={22} aria-hidden="true" />
          </div>
          <span>Add</span>
        </button>

        {PRIMARY_VIEWS.slice(2).map(({ id, label, Icon }) => {
          const isActive = view === id;
          return (
            <button
              key={id}
              id={`mob-nav-${id}`}
              className={`mobile-nav-item${isActive ? " active" : ""}`}
              onClick={() => navigateTo(id)}
              aria-label={label}
              aria-current={isActive ? "page" : undefined}
            >
              <div className="mob-icon-wrap">
                <Icon size={20} aria-hidden="true" />
                {isActive && <span className="mob-active-pip" />}
              </div>
              <span>{label}</span>
            </button>
          );
        })}
        <button
          id="mob-nav-more"
          className={`mobile-nav-item${moreDrawerOpen ? " active" : ""}`}
          onClick={() => setMoreDrawerOpen(true)}
          aria-label="More features"
        >
          <div className="mob-icon-wrap">
            <Grid size={20} aria-hidden="true" />
            {moreDrawerOpen && <span className="mob-active-pip" />}
          </div>
          <span>More</span>
        </button>
      </nav>

      {/* ── Mobile "More" Drawer (hidden on desktop via CSS) ── */}
      <div
        className={`sheet-backdrop mobile-more-backdrop${moreDrawerOpen ? " open" : ""}`}
        onClick={() => setMoreDrawerOpen(false)}
        aria-hidden="true"
      />
      <div
        className={`bottom-sheet mobile-more-drawer${moreDrawerOpen ? " open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="All features"
      >
        <div className="sheet-handle" />

        {/* User info strip */}
        <div className="drawer-user-info">
          <div style={{
            width: 44, height: 44, borderRadius: 14, background: gradient,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "white", fontWeight: 700, fontSize: 16, flexShrink: 0,
            overflow: "hidden",
          }}>
            {avatarUrl ? <img src={avatarUrl} alt="Avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="drawer-user-name">{displayName}</div>
            <div className="drawer-user-email">{session?.user?.email || profileData?.email}</div>
          </div>
          <button className="icon-btn" onClick={() => { navigateTo("profile"); setMoreDrawerOpen(false); }} aria-label="Go to profile">
            <User size={16} />
          </button>
        </div>

        {/* Quick actions */}
        <div className="drawer-section-label">Quick Actions</div>
        <div className="drawer-quick-actions">
          <button className="drawer-quick-btn" onClick={() => setSheetOpen(true) || setMoreDrawerOpen(false)}>
            <div className="drawer-quick-icon" style={{ background: "rgba(168,255,47,0.15)" }}><Plus size={18} style={{ color: "var(--primary)" }} /></div>
            <span>Add</span>
          </button>
          <button className="drawer-quick-btn" onClick={() => navigateTo("advisor")}>
            <div className="drawer-quick-icon" style={{ background: "rgba(111,96,255,0.15)" }}><Sparkles size={18} style={{ color: "var(--info)" }} /></div>
            <span>AI Chat</span>
          </button>
          <button className="drawer-quick-btn" onClick={() => navigateTo("analytics")}>
            <div className="drawer-quick-icon" style={{ background: "rgba(255,171,64,0.15)" }}><BarChart3 size={18} style={{ color: "var(--warning)" }} /></div>
            <span>Analytics</span>
          </button>
          <button className="drawer-quick-btn" onClick={() => navigateTo("credit")}>
            <div className="drawer-quick-icon" style={{ background: "rgba(255,59,48,0.15)" }}><Gauge size={18} style={{ color: "var(--negative)" }} /></div>
            <span>Health</span>
          </button>
        </div>

        {/* All pages */}
        <div className="drawer-section-label">All Pages</div>
        <div className="drawer-grid">
          {SECONDARY_VIEWS.map(({ id, label, Icon }) => (
            <button
              key={id}
              className={`drawer-page-btn${view === id ? " active" : ""}`}
              onClick={() => navigateTo(id)}
            >
              <Icon size={16} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
          <button
            className={`drawer-page-btn${view === "profile" ? " active" : ""}`}
            onClick={() => navigateTo("profile")}
          >
            <User size={16} aria-hidden="true" />
            <span>Profile</span>
          </button>
        </div>

        <button
          className="btn-secondary full-width"
          onClick={handleSignOut}
          style={{ color: "var(--negative)", marginTop: 8 }}
        >
          <LogOut size={16} /> Sign Out
        </button>
      </div>

      {/* ── Quick Add Sheet ── */}
      <QuickAddSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        onSaved={() => {
          toast("Transaction added ✓", "success");
          if (view !== "transactions") navigateTo("transactions");
        }}
      />

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} onNavigate={navigateTo} />
    </div>
  );
}

// ── Quick Add Sheet ────────────────────────────────────────────────────────────
function QuickAddSheet({ open, onClose, onSaved }) {
  const toast = useToast();
  const fileInputRef = React.useRef(null);
  const statementInputRef = React.useRef(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [scanning, setScanning] = React.useState(false);
  const [importMode, setImportMode] = React.useState("manual"); // "manual" or "sms"
  const [smsText, setSmsText] = React.useState("");
  const [amountStr, setAmountStr] = React.useState("0");
  const [accounts, setAccounts] = React.useState([]);
  const [categoryOptions, setCategoryOptions] = React.useState([]);
  const [pendingStatement, setPendingStatement] = React.useState(null);
  const [statementPreview, setStatementPreview] = React.useState(null);
  const [excludedStatementRows, setExcludedStatementRows] = React.useState(() => new Set());
  const [form, setForm] = React.useState({
    type: "expense", status: "posted", category: "Dining", description: "", date: today(), account: ""
  });

  useEffect(() => {
    if (open) {
      setAmountStr("0");
      setImportMode("manual");
      setSmsText("");
      setPendingStatement(null);
      setStatementPreview(null);
      setForm({ type: "expense", status: "posted", category: "Dining", description: "", date: today(), account: "" });
      apiFetch("/accounts").then((items) => {
        setAccounts(Array.isArray(items) ? items : []);
        if (items?.length) setForm((prev) => ({ ...prev, account: items[0].id }));
      }).catch(() => setAccounts([]));
      apiFetch("/categories").then((items) => setCategoryOptions(Array.isArray(items) ? items : [])).catch(() => setCategoryOptions([]));
    }
  }, [open]);

  const handleKeypad = (val) => {
    if (val === "back") {
      setAmountStr((prev) => (prev.length > 1 ? prev.slice(0, -1) : "0"));
      return;
    }
    if (val === ".") {
      if (!amountStr.includes(".")) setAmountStr((prev) => prev + ".");
      return;
    }
    setAmountStr((prev) => (prev === "0" ? val : prev + val));
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setScanning(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiFetch("/receipts/scan", { method: "POST", body: formData });
      
      setAmountStr(String(res.amount));
      setForm(prev => ({
        ...prev, 
        type: "expense", 
        description: res.description, 
        category: res.category || prev.category,
        date: res.date || prev.date
      }));
      toast("Receipt scanned successfully!", "success");
    } catch (err) {
      toast(err.message || "Failed to scan receipt", "error");
    } finally {
      setScanning(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleStatementChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (form.account) formData.append("account_id", form.account);
      toast("Reading statement for review...", "info");
      const preview = await apiFetch("/imports/statement/preview", { method: "POST", body: formData });
      setPendingStatement(file);
      setStatementPreview(preview);
      setExcludedStatementRows(new Set());
    } catch (err) {
      toast(err.message || "Failed to upload statement", "error");
    } finally {
      if (statementInputRef.current) statementInputRef.current.value = "";
    }
  };

  const confirmStatementImport = async () => {
    if (!pendingStatement) return;
    try {
      const formData = new FormData();
      formData.append("file", pendingStatement);
      if (form.account) formData.append("account_id", form.account);
      formData.append("excluded_row_fingerprints", JSON.stringify([...excludedStatementRows]));
      const job = await apiFetch("/imports/statement", { method: "POST", body: formData });
      if (job.status === "done") {
        toast("This statement was already imported; no duplicate rows were added.", "info");
      } else if (job.status === "failed") {
        toast("This statement was already attempted and failed. Review the import status and retry it.", "error");
      } else {
        toast("Statement processing started.", "success");
      }
      onSaved();
      onClose();
    } catch (err) {
      toast(err.message || "Failed to import statement", "error");
    }
  };

  const submitSms = async () => {
    const messages = smsText.split(/\n+/).map(l => l.trim()).filter(Boolean);
    if (!messages.length) return toast("Enter SMS text first", "error");
    setSubmitting(true);
    try {
      await apiFetch("/imports/sms", { method: "POST", body: JSON.stringify({ messages }) });
      toast("SMS imported successfully", "success");
      onSaved();
      onClose();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  async function save(e) {
    if (e) e.preventDefault();
    const numericAmount = Number(amountStr);
    if (!numericAmount || numericAmount <= 0) return toast("Enter a valid amount", "error");
    
    setSubmitting(true);
    try {
      await apiFetch("/transactions", {
        method: "POST",
        body: JSON.stringify({ 
          type: form.type,
          status: form.status,
          amount: numericAmount,
          category: form.category,
          description: form.description || "Quick Add",
          date: form.date,
          source: form.account ? "bank" : "cash",
          account_id: form.account || null,
        }),
      });
      onSaved();
      onClose();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSubmitting(false);
    }
  }

  const configuredCategories = categoryOptions
    .filter((item) => item.is_active && item.kind === (form.type === "income" ? "income" : "expense"))
    .map((item) => item.name);
  const fallbackCategories = form.type === "income" ? ["Salary", "Freelance", "Other"]
    : ["refund", "reimbursement"].includes(form.type) ? ["Refunds", "Shopping", "Dining", "Other"]
    : form.type === "transfer" ? ["Transfer", "Other"]
    : ["Dining", "Groceries", "Transport", "Shopping", "Health", "Housing"];
  const activeCategories = configuredCategories.length ? configuredCategories : fallbackCategories;

  // Automatically ensure category is valid for type
  useEffect(() => {
    if (!activeCategories.includes(form.category)) {
      setForm((prev) => ({ ...prev, category: activeCategories[0] }));
    }
  }, [form.type]);

  return (
    <>
      <div className={`sheet-backdrop${open ? " open" : ""}`} onClick={onClose} aria-hidden="true" />
      <section
        className={`bottom-sheet add-sheet${open ? " open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="Add Transaction"
        aria-hidden={!open}
      >
        <div className="sheet-handle" />

        <div className="add-content">
          {/* Segmented Control */}
          <div className="add-segmented-control">
            <button className={form.type === "expense" ? "active" : ""} onClick={() => setForm({ ...form, type: "expense" })}>Expense</button>
            <button className={form.type === "income" ? "active" : ""} onClick={() => setForm({ ...form, type: "income" })}>Income</button>
            <button className={form.type === "refund" ? "active" : ""} onClick={() => setForm({ ...form, type: "refund" })}>Refund</button>
            <button className={form.type === "reimbursement" ? "active" : ""} onClick={() => setForm({ ...form, type: "reimbursement" })}>Reimbursement</button>
            <button className={form.type === "transfer" ? "active" : ""} onClick={() => setForm({ ...form, type: "transfer" })}>Transfer</button>
          </div>

          {/* Amount Display */}
          <div className="add-amount-display">
            <span className="add-currency">₹</span>
            {amountStr}
          </div>
          <div className="add-amount-hint">Tap the keypad, scan a receipt, or import</div>

          {/* Action Buttons */}
          <div className="add-action-buttons">
            <input type="file" accept="image/*" ref={fileInputRef} style={{ display: "none" }} onChange={handleFileChange} />
            <input type="file" accept=".csv,.xls,.xlsx,.ods,.pdf" ref={statementInputRef} style={{ display: "none" }} onChange={handleStatementChange} />
            <button className="add-action-btn" type="button" onClick={() => { setImportMode("manual"); fileInputRef.current?.click(); }} disabled={scanning}>
              {scanning ? <Loader2 size={16} className="spin" /> : <Scan size={16} />} 
              {scanning ? "Scanning..." : "Receipt"}
            </button>
            <button className="add-action-btn" type="button" onClick={() => { setImportMode("manual"); statementInputRef.current?.click(); }} disabled={scanning}>
              <FileText size={16} /> Statement
            </button>
            <button className={`add-action-btn ${importMode === "sms" ? "active" : ""}`} type="button" onClick={() => setImportMode(importMode === "sms" ? "manual" : "sms")} disabled={scanning}>
              <MessageSquare size={16} /> SMS
            </button>
          </div>

          {statementPreview ? (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="add-section-label">REVIEW STATEMENT</div>
              <div style={{ padding: "14px 16px", borderRadius: 14, background: "var(--surface-secondary)", border: "1px solid var(--border)" }}>
                <div style={{ fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>{statementPreview.file_name}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {statementPreview.row_count} rows found · {statementPreview.duplicate_count} will be skipped · {form.account ? "Account selected" : "No account selected"}
                </div>
              </div>
              {statementPreview.warnings?.map((warning) => (
                <div key={warning} style={{ fontSize: 12, lineHeight: 1.45, color: "var(--text-secondary)", padding: "9px 11px", borderRadius: 10, background: "rgba(250,204,21,0.10)", border: "1px solid rgba(250,204,21,0.28)" }}>
                  {warning}
                </div>
              ))}
              <div style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 12 }}>
                {statementPreview.preview?.slice(0, 20).map((row, index) => {
                  const excluded = excludedStatementRows.has(row.fingerprint);
                  const uncertain = row.category_confidence != null && row.category_confidence < 0.6;
                  return (
                  <label key={`${row.fingerprint || row.date}-${index}`} style={{ display: "flex", gap: 10, alignItems: "center", padding: "9px 11px", borderBottom: "1px solid var(--border)", opacity: row.duplicate || excluded ? 0.5 : 1, fontSize: 12, cursor: row.duplicate ? "default" : "pointer" }}>
                    <input type="checkbox" checked={!excluded && !row.duplicate} disabled={row.duplicate} onChange={() => setExcludedStatementRows((previous) => {
                      const next = new Set(previous);
                      if (next.has(row.fingerprint)) next.delete(row.fingerprint); else next.add(row.fingerprint);
                      return next;
                    })} aria-label={`${excluded ? "Include" : "Exclude"} ${row.description}`} />
                    <span style={{ width: 76, color: "var(--text-muted)" }}>{row.date}</span>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-primary)" }}>{row.description}</span>
                    <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>₹{row.amount}</span>
                    {row.duplicate && <span style={{ color: "var(--text-muted)", fontSize: 10 }}>SKIP</span>}
                    {!row.duplicate && row.category && <span style={{ color: "var(--text-muted)", fontSize: 10 }}>{row.category}{uncertain ? " · REVIEW" : ""}</span>}
                  </label>
                  );
                })}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {excludedStatementRows.size ? `${excludedStatementRows.size} row(s) excluded from this import. You can repair them later from Activity.` : "Uncheck any row you do not want to import. Low-confidence categories are marked REVIEW."}
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: "auto" }}>
                <button className="btn-secondary" onClick={() => { setPendingStatement(null); setStatementPreview(null); setExcludedStatementRows(new Set()); }}>Choose another</button>
                <button className="add-submit-btn" onClick={confirmStatementImport} disabled={!statementPreview.row_count || statementPreview.duplicate_count + excludedStatementRows.size >= statementPreview.row_count}>
                  Confirm import
                </button>
              </div>
            </div>
          ) : importMode === "sms" ? (
            <div className="sms-import-view" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              <div className="add-section-label">PASTE SMS MESSAGES</div>
              <textarea 
                style={{ padding: "16px 20px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 20, width: "100%", height: 200, resize: "none", color: "var(--text-primary)", fontFamily: "inherit", fontSize: 15, marginBottom: 24, outline: "none" }}
                placeholder="Paste UPI / bank SMS messages here (one per line)..."
                value={smsText}
                onChange={e => setSmsText(e.target.value)}
              />
              <button className="add-submit-btn" onClick={submitSms} disabled={submitting || !smsText.trim()}>
                {submitting ? <><Loader2 size={16} className="spin" /> Parsing…</> : "Import SMS"}
              </button>
            </div>
          ) : (
            <>
              {/* Categories */}
              <div className="add-section-label">CATEGORY</div>
              <div className="add-categories-wrap">
                {activeCategories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    className={`category-pill${form.category === cat ? " active" : ""}`}
                    onClick={() => setForm({ ...form, category: cat })}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              {/* Form List Fields */}
              <div className="add-form-list">
                <label className="add-form-row">
                  <span className="row-label">Account</span>
                  <select className="row-input" value={form.account} onChange={e => setForm({...form, account: e.target.value})}>
                    <option value="">Cash wallet</option>
                    {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                  </select>
                </label>
                <label className="add-form-row">
                  <span className="row-label">Date</span>
                  <input type="date" className="row-input" value={form.date} onChange={e => setForm({...form, date: e.target.value})} />
                </label>
                <label className="add-form-row">
                  <span className="row-label">Status</span>
                  <select className="row-input" value={form.status} onChange={e => setForm({...form, status: e.target.value})}>
                    <option value="posted">Posted · include in totals</option>
                    <option value="pending">Pending · review later</option>
                    <option value="excluded">Excluded · keep for records</option>
                  </select>
                </label>
                <label className="add-form-row">
                  <span className="row-label">Note</span>
                  <input type="text" className="row-input placeholder-right" placeholder="Add a note" value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
                </label>
              </div>

              {/* Custom Keypad */}
              <div className="custom-keypad">
                {["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0"].map((key) => (
                  <button key={key} type="button" className="keypad-btn" onClick={() => handleKeypad(key)}>{key}</button>
                ))}
                <button type="button" className="keypad-btn" onClick={() => handleKeypad("back")}>
                  <Delete size={22} />
                </button>
              </div>

              {/* Submit */}
              <button className="add-submit-btn" onClick={save} disabled={submitting || amountStr === "0" || amountStr === "0."}>
                {submitting ? <><Loader2 size={16} className="spin" /> Saving…</> : "Enter an amount"}
              </button>
            </>
          )}
        </div>
      </section>
    </>
  );
}
