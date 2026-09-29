import React, { useState, useEffect, useRef, lazy, Suspense } from "react";
import { apiFetch, API_BASE, EXPENSE_CATEGORIES, currencySymbol, getCurrencyPreference, money, moneyInCurrency, setAuthToken, setCurrencyPreference, setDisplayRates, setRegionPreference, today } from "./lib";
import { clearGoogleSession, loadGoogleSession } from "./googleAuth";
import { useToast, LedgerLogo, CardSkeleton } from "./components/ui";
import Auth from "./views/Auth";
import CommandPalette from "./components/CommandPalette";
import { listQueued, queueCapture, removeQueued, updateQueued } from "./offlineQueue";

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
  const [transactionInitialFilter, setTransactionInitialFilter] = useState("All");
  const [cmdOpen, setCmdOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [moreDrawerOpen, setMoreDrawerOpen] = useState(false);
  const [session, setSession] = useState(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [profileData, setProfileData] = useState(null);
  const moreDrawerRef = useRef(null);
  const moreTriggerRef = useRef(null);

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

    loadGoogleSession().then(setSession).catch(() => setSession(null)).finally(() => setLoadingAuth(false));
  }, []);

  useEffect(() => {
    if (!session) return;
    Promise.all([apiFetch("/profile"), apiFetch("/accounts").catch(() => [])]).then(([profile, accounts]) => {
      setProfileData(profile);
      localStorage.setItem("ledger-last-profile-id", profile.id);
      setCurrencyPreference(profile.currency_preference);
      setRegionPreference(profile.region);
      const accountCurrency = Array.isArray(accounts) && accounts.length > 0 ? accounts[0].currency : null;
      const savedRecordCurrency = localStorage.getItem("ledger-record-currency");
      // Existing accounts are the most reliable source for legacy records. If
      // the preferred currency differs, do not trust a stale browser cache.
      const recordCurrency = accountCurrency && accountCurrency !== profile.currency_preference
        ? accountCurrency
        : savedRecordCurrency || accountCurrency || profile.currency_preference;
      localStorage.setItem("ledger-record-currency", recordCurrency);
      apiFetch(`/currency/rates?base=${recordCurrency}`)
        .then((rates) => setDisplayRates(rates.base, rates.rates, rates.date))
        .catch(() => {});
    }).catch(() => {});
  }, [session]);

  useEffect(() => {
    if (session) startKeepAlive(); else stopKeepAlive();
  }, [session]);

  useEffect(() => {
    const expired = () => { setSession(null); setProfileData(null); setAuthToken(null); };
    window.addEventListener("ledger-session-expired", expired);
    return () => window.removeEventListener("ledger-session-expired", expired);
  }, []);

  // Close more drawer on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") { setMoreDrawerOpen(false); setSheetOpen(false); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!moreDrawerOpen) return undefined;
    const focusTimer = window.setTimeout(() => moreDrawerRef.current?.querySelector("button")?.focus(), 30);
    const onKeyDown = (event) => {
      if (event.key !== "Tab") return;
      const elements = [...(moreDrawerRef.current?.querySelectorAll("button:not([disabled]), a[href]") || [])]
        .filter((element) => element.getClientRects().length > 0);
      if (!elements.length) return;
      if (event.shiftKey && document.activeElement === elements[0]) { event.preventDefault(); elements[elements.length - 1].focus(); }
      else if (!event.shiftKey && document.activeElement === elements[elements.length - 1]) { event.preventDefault(); elements[0].focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { window.clearTimeout(focusTimer); document.removeEventListener("keydown", onKeyDown); moreTriggerRef.current?.focus(); };
  }, [moreDrawerOpen]);

  const handleSignOut = async () => {
    if (import.meta.env.VITE_AUTH_PROVIDER === "dev") {
      stopKeepAlive();
      localStorage.removeItem("ledger-last-profile-id");
      setProfileData(null);
      localStorage.removeItem("dev-session"); setSession(null); setAuthToken(null); return;
    }
    try {
      await clearGoogleSession();
    } catch (error) {
      toast(error.message || "Could not sign out. Please try again.", "error");
      return;
    }
    stopKeepAlive();
    localStorage.removeItem("ledger-last-profile-id");
    setProfileData(null);
    setSession(null);
    setAuthToken(null);
  };

  const renderView = () => {
    switch (view) {
      case "dashboard":    return <Dashboard userName={displayName} onNavigate={navigateTo} onAddTransaction={() => setSheetOpen(true)} />;
      case "transactions": return <Transactions initialFilter={transactionInitialFilter} />;
      case "budgets":      return <Budgets onNavigate={navigateTo} />;
      case "goals":        return <Goals />;
      case "analytics":    return <Analytics onNavigate={navigateTo} />;
      case "accounts":     return <Accounts />;
      case "investments":  return <Investments />;
      case "credit":       return <CreditBenchmarks />;
      case "export":       return <ExportGST />;
      case "audit":        return <AuditWebhooks />;
      case "advisor":      return <Advisor onNavigate={navigateTo} />;
      case "profile":      return <Profile onSignOut={handleSignOut} />;
      default:             return <Dashboard userName={displayName} onNavigate={navigateTo} onAddTransaction={() => setSheetOpen(true)} />;
    }
  };

  function navigateTo(id, options = {}) {
    setView(id);
    setTransactionInitialFilter(options.filter || "All");
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
          ref={moreTriggerRef}
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
        ref={moreDrawerRef}
        hidden={!moreDrawerOpen}
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
        ownerId={profileData?.id || localStorage.getItem("ledger-last-profile-id")}
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
function QuickAddSheet({ open, onClose, onSaved, ownerId }) {
  const toast = useToast();
  const fileInputRef = React.useRef(null);
  const statementInputRef = React.useRef(null);
  const sheetRef = React.useRef(null);
  const amountRef = React.useRef(null);
  const priorFocusRef = React.useRef(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [scanning, setScanning] = React.useState(false);
  const [importMode, setImportMode] = React.useState("manual"); // "manual" or "sms"
  const [smsText, setSmsText] = React.useState("");
  const [amountStr, setAmountStr] = React.useState("0");
  const [accounts, setAccounts] = React.useState([]);
  const [categoryOptions, setCategoryOptions] = React.useState([]);
  const [merchantOptions, setMerchantOptions] = React.useState([]);
  const [merchantCategories, setMerchantCategories] = React.useState({});
  const [recurringEnabled, setRecurringEnabled] = React.useState(false);
  const [recurringCadence, setRecurringCadence] = React.useState("monthly");
  const [nextDue, setNextDue] = React.useState("");
  const [receiptFile, setReceiptFile] = React.useState(null);
  const [queuedDrafts, setQueuedDrafts] = React.useState([]);
  const [syncingDrafts, setSyncingDrafts] = React.useState(false);
  const [online, setOnline] = React.useState(navigator.onLine);
  const [splitEnabled, setSplitEnabled] = React.useState(false);
  const [splitLines, setSplitLines] = React.useState([
    { category: "Dining", amount: "" }, { category: "Groceries", amount: "" },
  ]);
  const [pendingStatement, setPendingStatement] = React.useState(null);
  const [statementPreview, setStatementPreview] = React.useState(null);
  const [excludedStatementRows, setExcludedStatementRows] = React.useState(() => new Set());
  const [statementEdits, setStatementEdits] = React.useState({});
  const [form, setForm] = React.useState({
    type: "expense", status: "posted", category: "Dining", description: "", date: today(), account: ""
  });
  const activeCurrency = accounts.find((account) => account.id === form.account)?.currency || getCurrencyPreference();

  useEffect(() => {
    if (open) {
      priorFocusRef.current = document.activeElement;
      const focusTimer = window.setTimeout(() => amountRef.current?.focus(), 30);
      setAmountStr("0");
      setImportMode("manual");
      setSmsText("");
      setPendingStatement(null);
      setStatementPreview(null);
      setStatementEdits({});
      setRecurringEnabled(false);
      setRecurringCadence("monthly");
      setNextDue("");
      setReceiptFile(null);
      setSplitEnabled(false);
      setSplitLines([{ category: "Dining", amount: "" }, { category: "Groceries", amount: "" }]);
      setForm({ type: "expense", status: "posted", category: "Dining", description: "", date: today(), account: "" });
      apiFetch("/accounts").then((items) => {
        setAccounts(Array.isArray(items) ? items : []);
        if (items?.length) setForm((prev) => ({ ...prev, account: items[0].id }));
      }).catch(() => setAccounts([]));
      apiFetch("/categories").then((items) => setCategoryOptions(Array.isArray(items) ? items : [])).catch(() => setCategoryOptions([]));
      listQueued(ownerId).then(setQueuedDrafts).catch(() => setQueuedDrafts([]));
      Promise.all([
        apiFetch("/merchant-aliases").catch(() => []),
        apiFetch("/transactions?limit=50").catch(() => ({ items: [] })),
      ]).then(([aliases, recent]) => {
        const names = [...aliases.map((item) => item.canonical), ...(recent.items || []).map((item) => item.merchant_normalized || item.description)];
        setMerchantOptions([...new Set(names.filter(Boolean))].slice(0, 30));
        setMerchantCategories(Object.fromEntries([...(recent.items || [])].reverse()
          .filter((item) => item.type === "expense")
          .map((item) => [(item.merchant_normalized || item.description).toLocaleLowerCase(), item.category])));
      });
      const onKeyDown = (event) => {
        if (event.key === "Escape") { event.preventDefault(); onClose(); }
        if (event.key !== "Tab") return;
        const elements = [...sheetRef.current.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])")]
          .filter((element) => element.getClientRects().length > 0);
        if (!elements.length) return;
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      };
      document.addEventListener("keydown", onKeyDown);
      return () => {
        window.clearTimeout(focusTimer);
        document.removeEventListener("keydown", onKeyDown);
        priorFocusRef.current?.focus?.();
      };
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    const refresh = () => setOnline(navigator.onLine);
    window.addEventListener("online", refresh);
    window.addEventListener("offline", refresh);
    return () => { window.removeEventListener("online", refresh); window.removeEventListener("offline", refresh); };
  }, []);

  useEffect(() => {
    if (open) listQueued(ownerId).then(setQueuedDrafts).catch(() => setQueuedDrafts([]));
  }, [open, ownerId]);

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
    if (file.size > 5 * 1024 * 1024) return toast("Receipt must be under 5MB", "error");
    setReceiptFile(file);
    if (file.type === "application/pdf") {
      toast("PDF receipt attached. Its details were not scanned; enter them manually.", "info");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    
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
      toast(`${err.message || "Could not scan receipt"}. The file is still attached for saving.`, "info");
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
      setStatementEdits({});
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
      formData.append("review_overrides", JSON.stringify(statementEdits));
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

  async function submitCapture(submission) {
    const saved = await apiFetch(submission.path, { method: "POST", body: JSON.stringify(submission.payload) });
    if (submission.receiptFile) {
      const attachment = new FormData();
      attachment.append("file", submission.receiptFile);
      const txId = submission.path.endsWith("/split") ? saved.items[0].id : saved.id;
      await apiFetch(`/transactions/${txId}/receipt`, { method: "POST", body: attachment });
    }
    if (submission.recurringTemplate) {
      await apiFetch("/recurring", {
        method: "POST",
        body: JSON.stringify({ ...submission.recurringTemplate, evidence_transaction_ids: [saved.id] }),
      });
    }
    return saved;
  }

  async function syncDrafts() {
    if (!ownerId || !navigator.onLine) return;
    setSyncingDrafts(true);
    try {
      const currentProfile = await apiFetch("/profile");
      if (currentProfile.id !== ownerId) throw new Error("These offline entries belong to another profile; they were not sent.");
      let completed = 0;
      for (const draft of await listQueued(ownerId)) {
        try {
          await submitCapture(draft);
          await removeQueued(draft.id);
          completed += 1;
        } catch (error) {
          await updateQueued({ ...draft, status: "needs_retry", error: String(error.message || error).slice(0, 160) });
        }
      }
      setQueuedDrafts(await listQueued(ownerId));
      toast(completed ? `${completed} offline entr${completed === 1 ? "y" : "ies"} synced` : "No entries synced; check the retry status below", completed ? "success" : "info");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setSyncingDrafts(false);
    }
  }

  async function discardDraft(id) {
    if (!window.confirm("Discard this unsynced entry? It cannot be recovered.")) return;
    try {
      await removeQueued(id);
      setQueuedDrafts(await listQueued(ownerId));
    } catch (error) { toast(error.message, "error"); }
  }

  async function save(e) {
    if (e) e.preventDefault();
    const numericAmount = Number(amountStr);
    if (!numericAmount || numericAmount <= 0) return toast("Enter a valid amount", "error");
    if (splitEnabled) {
      const lineCents = splitLines.reduce((total, line) => total + Math.round(Number(line.amount) * 100), 0);
      if (splitLines.some((line) => !Number(line.amount) || !line.category) || lineCents !== Math.round(numericAmount * 100)) {
        return toast("Split lines must add up exactly to the total", "error");
      }
    }
    const requestId = crypto.randomUUID();
    const submission = {
      path: splitEnabled ? "/transactions/split" : "/transactions",
      payload: splitEnabled ? {
        status: form.status, amount: amountStr, description: form.description || "Split purchase",
        date: form.date, account_id: form.account || null, lines: splitLines,
        client_request_id: requestId,
      } : {
        type: form.type, status: form.status, amount: amountStr,
        category: form.category, description: form.description || "Quick Add", date: form.date,
        source: form.account ? "bank" : "cash", account_id: form.account || null,
        source_ref: `offline:${requestId}`,
      },
      receiptFile,
      recurringTemplate: recurringEnabled && !splitEnabled && form.type === "expense" && form.status === "posted"
        ? { description: form.description.trim(), category: form.category, cadence: recurringCadence,
            average_amount: amountStr, minimum_amount: amountStr, maximum_amount: amountStr,
            next_expected: nextDue, confidence: 1, status: "active", confirmed: true }
        : null,
    };
    setSubmitting(true);
    try {
      if (!navigator.onLine) {
        await queueCapture(ownerId, submission);
        setQueuedDrafts(await listQueued(ownerId));
        toast("Entry saved on this device. Sync it when connected.", "info");
        onClose();
        return;
      }
      await submitCapture(submission);
      onSaved();
      onClose();
    } catch (error) {
      if (!navigator.onLine || error instanceof TypeError) {
        try {
          await queueCapture(ownerId, submission);
          setQueuedDrafts(await listQueued(ownerId));
          toast("Connection lost. Entry queued on this device for explicit sync.", "info");
          onClose();
        } catch (queueError) { toast(queueError.message, "error"); }
      } else {
        toast(error.message, "error");
      }
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
    if (form.type !== "expense") setSplitEnabled(false);
  }, [form.type]);

  return (
    <>
      <div className={`sheet-backdrop${open ? " open" : ""}`} onClick={onClose} aria-hidden="true" />
      <section
        ref={sheetRef}
        hidden={!open}
        className={`bottom-sheet add-sheet${open ? " open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="Add Transaction"
        aria-hidden={!open}
      >
        <div className="sheet-handle" />
        <button className="btn-secondary" type="button" onClick={onClose} aria-label="Close quick add" style={{ alignSelf: "flex-end", marginBottom: 8 }}><X size={16} /> Close</button>

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
            <span className="add-currency">{currencySymbol(activeCurrency)}</span>
            <input ref={amountRef} aria-label={`Amount in ${activeCurrency}`} inputMode="decimal" type="text" value={amountStr}
              onChange={(event) => {
                const cleaned = event.target.value.replace(/[^0-9.]/g, "");
                if (/^\d{0,10}(?:\.\d{0,2})?$/.test(cleaned)) setAmountStr(cleaned || "0");
              }}
              style={{ width: "100%", minWidth: 0, background: "transparent", border: 0, color: "inherit", font: "inherit", outlineOffset: 4 }} />
          </div>
          <div className="add-amount-hint">Tap the keypad, scan a receipt, or import</div>
          {receiptFile && <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, fontSize: 12, color: "var(--text-secondary)", marginTop: 6 }}>
            <span>Receipt attached: {receiptFile.name}</span>
            <button type="button" className="btn-secondary" onClick={() => setReceiptFile(null)}>Remove</button>
          </div>}

          {/* Action Buttons */}
          <div className="add-action-buttons">
            <input type="file" accept="image/png,image/jpeg,image/webp,application/pdf" ref={fileInputRef} style={{ display: "none" }} onChange={handleFileChange} />
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
          {queuedDrafts.length > 0 && <section aria-label="Unsynced quick captures" style={{ padding: 12, border: "1px solid var(--warning)", borderRadius: 12, margin: "10px 0", color: "var(--text-primary)" }}>
            <strong>{queuedDrafts.length} entr{queuedDrafts.length === 1 ? "y" : "ies"} saved on this device</strong>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "6px 0" }}>They do not affect balances or budgets until you sync them. Nothing is sent automatically.</p>
            {queuedDrafts.map((draft) => <div key={draft.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", fontSize: 12 }}>
              <span style={{ flex: 1 }}>{draft.payload.description} · {moneyInCurrency(draft.payload.amount, activeCurrency)} · {draft.status === "needs_retry" ? `Needs retry: ${draft.error || "sync failed"}` : "Queued"}</span>
              <button type="button" className="btn-secondary" disabled={syncingDrafts} onClick={() => discardDraft(draft.id)} aria-label={`Discard unsynced ${draft.payload.description}`}>Discard</button>
            </div>)}
            <button type="button" className="btn-primary" disabled={!online || syncingDrafts} onClick={syncDrafts}>
              {syncingDrafts ? "Syncing…" : online ? "Sync queued entries" : "Connect to sync"}
            </button>
          </section>}

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
              <div style={{ maxHeight: 300, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 12 }}>
                {statementPreview.preview?.slice(0, 20).map((row, index) => {
                  const excluded = excludedStatementRows.has(row.fingerprint);
                  const uncertain = row.category_confidence != null && row.category_confidence < 0.6;
                  const edit = statementEdits[row.fingerprint] || {};
                  const category = edit.category ?? row.category ?? "Other";
                  const merchant = edit.merchant_normalized ?? row.merchant_normalized ?? "";
                  const type = edit.type ?? row.type ?? "expense";
                  const importCategories = [...new Set([
                    ...EXPENSE_CATEGORIES,
                    ...categoryOptions.map((item) => item.name || item).filter(Boolean),
                    category,
                  ])];
                  const updateEdit = (key, value) => setStatementEdits((previous) => ({
                    ...previous,
                    [row.fingerprint]: { ...previous[row.fingerprint], [key]: value },
                  }));
                  return (
                  <div key={`${row.fingerprint || row.date}-${index}`} style={{ display: "grid", gridTemplateColumns: "auto 76px minmax(100px, 1fr) 95px 120px 92px auto", gap: 8, alignItems: "center", padding: "9px 11px", borderBottom: "1px solid var(--border)", opacity: row.duplicate || excluded ? 0.5 : 1, fontSize: 12 }}>
                    <input type="checkbox" checked={!excluded && !row.duplicate} disabled={row.duplicate} onChange={() => setExcludedStatementRows((previous) => {
                      const next = new Set(previous);
                      if (next.has(row.fingerprint)) next.delete(row.fingerprint); else next.add(row.fingerprint);
                      return next;
                    })} aria-label={`${excluded ? "Include" : "Exclude"} ${row.description}`} />
                    <span style={{ width: 76, color: "var(--text-muted)" }}>{row.date}</span>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-primary)" }}>{row.description}</span>
                    <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{moneyInCurrency(row.amount, activeCurrency)}</span>
                    <input value={merchant} disabled={row.duplicate} onChange={(event) => updateEdit("merchant_normalized", event.target.value)} placeholder="Merchant" aria-label={`Merchant for ${row.description}`} style={{ minWidth: 0, width: "100%", padding: "5px 6px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)" }} />
                    <select value={category} disabled={row.duplicate} onChange={(event) => updateEdit("category", event.target.value)} aria-label={`Category for ${row.description}`} style={{ minWidth: 0, width: "100%", padding: "5px 4px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)" }}>
                      {importCategories.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                    <select value={type} disabled={row.duplicate} onChange={(event) => updateEdit("type", event.target.value)} aria-label={`Type for ${row.description}`} style={{ minWidth: 0, width: "100%", padding: "5px 4px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)" }}>
                      {['expense', 'income', 'refund', 'reimbursement', 'transfer'].map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                    {row.duplicate && <span style={{ color: "var(--text-muted)", fontSize: 10 }}>SKIP</span>}
                    {!row.duplicate && row.category && <span style={{ color: "var(--text-muted)", fontSize: 10 }}>{uncertain ? "REVIEW" : "Edited"}</span>}
                  </div>
                  );
                })}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {excludedStatementRows.size ? `${excludedStatementRows.size} row(s) excluded from this import. You can repair them later from Activity.` : "Edit merchant, category, or type before confirming. Low-confidence categories are marked REVIEW."}
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
                  <span className="row-label">Merchant / description</span>
                  <input type="text" className="row-input placeholder-right" list="quick-add-merchants" placeholder="Who was this with?" value={form.description} onChange={(event) => {
                    const description = event.target.value;
                    const suggestedCategory = merchantCategories[description.toLocaleLowerCase()];
                    setForm((previous) => ({ ...previous, description, category: suggestedCategory || previous.category }));
                  }} />
                  <datalist id="quick-add-merchants">{merchantOptions.map((name) => <option key={name} value={name} />)}</datalist>
                </label>
                {form.type === "expense" && <>
                  <label className="add-form-row"><span className="row-label">Split categories</span><input type="checkbox" checked={splitEnabled} onChange={(event) => {
                    setSplitEnabled(event.target.checked);
                    if (event.target.checked) setSplitLines([{ category: activeCategories[0], amount: "" }, { category: activeCategories[1] || activeCategories[0], amount: "" }]);
                  }} /></label>
                  {splitEnabled && <div style={{ padding: "8px 12px", color: "var(--text-secondary)", fontSize: 12 }}>
                    {splitLines.map((line, index) => <div key={index} style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                      <select aria-label={`Split ${index + 1} category`} value={line.category} onChange={(event) => setSplitLines((rows) => rows.map((item, i) => i === index ? { ...item, category: event.target.value } : item))}>
                        {activeCategories.map((category) => <option key={category} value={category}>{category}</option>)}
                      </select>
                      <input aria-label={`Split ${index + 1} amount`} type="number" min="0.01" step="0.01" value={line.amount} onChange={(event) => setSplitLines((rows) => rows.map((item, i) => i === index ? { ...item, amount: event.target.value } : item))} style={{ width: 110 }} />
                      {splitLines.length > 2 && <button type="button" className="btn-secondary" aria-label={`Remove split ${index + 1}`} onClick={() => setSplitLines((rows) => rows.filter((_, i) => i !== index))}>−</button>}
                    </div>)}
                    {splitLines.length < 10 && <button type="button" className="btn-secondary" onClick={() => setSplitLines((rows) => [...rows, { category: activeCategories[0], amount: "" }])}>Add category</button>}
                    <div style={{ marginTop: 6 }}>Assigned: {moneyInCurrency(splitLines.reduce((total, line) => total + Number(line.amount || 0), 0), activeCurrency)} of {moneyInCurrency(amountStr, activeCurrency)}. The receipt attaches to the first split line.</div>
                  </div>}
                </>}
                {form.type === "expense" && form.status === "posted" && !splitEnabled && <>
                  <label className="add-form-row"><span className="row-label">Repeat this payment</span><input type="checkbox" checked={recurringEnabled} onChange={(event) => setRecurringEnabled(event.target.checked)} /></label>
                  {recurringEnabled && <>
                    <label className="add-form-row"><span className="row-label">Repeat</span><select className="row-input" value={recurringCadence} onChange={(event) => setRecurringCadence(event.target.value)}><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option></select></label>
                    <label className="add-form-row"><span className="row-label">Next due date</span><input className="row-input" type="date" min={today()} value={nextDue} onChange={(event) => setNextDue(event.target.value)} /></label>
                  </>}
                </>}
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
              <button className="add-submit-btn" onClick={save} disabled={submitting || !Number(amountStr) || (recurringEnabled && !splitEnabled && form.type === "expense" && form.status === "posted" && (!nextDue || !form.description.trim()))}>
                {submitting ? <><Loader2 size={16} className="spin" /> Saving…</> : "Enter an amount"}
              </button>
            </>
          )}
        </div>
      </section>
    </>
  );
}
