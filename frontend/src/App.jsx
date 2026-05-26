import React, { useState, useEffect, useRef, useCallback, lazy, Suspense } from "react";
import { supabase } from "./supabase";
import { apiFetch, API_BASE, EXPENSE_CATEGORIES, setAuthToken, today } from "./lib";
import { useToast, LegerLogo, CardSkeleton } from "./components/ui";
import Auth from "./views/Auth";
import CommandPalette from "./components/CommandPalette";

// ── Lazy-load heavy views for Vercel bundle splitting ─────────────────────────
const Dashboard     = lazy(() => import("./views/Dashboard"));
const Transactions  = lazy(() => import("./views/Transactions"));
const Budgets       = lazy(() => import("./views/Budgets"));
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
  Wallet, Download, Shield, Command, Briefcase, Gauge, LogOut,
  Loader2, X, MoreHorizontal, Grid, User, ChevronDown,
} from "lucide-react";

const PRIMARY_VIEWS = [
  { id: "dashboard",    label: "Dashboard",    Icon: LayoutDashboard },
  { id: "transactions", label: "Transactions", Icon: Plus },
  { id: "budgets",      label: "Budgets",      Icon: Target },
  { id: "investments",  label: "Investments",  Icon: Briefcase },
  { id: "credit",       label: "Health",       Icon: Gauge },
  { id: "advisor",      label: "Amadeus AI",   Icon: Sparkles },
];

const SECONDARY_VIEWS = [
  { id: "accounts",  label: "Accounts",    Icon: Wallet },
  { id: "analytics", label: "Analytics",   Icon: BarChart3 },
  { id: "export",    label: "Export & GST", Icon: Download },
  { id: "audit",     label: "Audit Logs",  Icon: Shield },
];

const ALL_VIEWS = [...PRIMARY_VIEWS, ...SECONDARY_VIEWS];

// ── Keep-alive pinger to prevent Render free-tier cold starts ─────────────────
let _pingInterval = null;
function startKeepAlive() {
  if (_pingInterval) return;
  _pingInterval = setInterval(async () => {
    try { await fetch(`${API_BASE}/ping`); } catch { /* noop */ }
  }, 13 * 60 * 1000); // every 13 minutes (Render sleeps after 15)
}
function stopKeepAlive() {
  if (_pingInterval) { clearInterval(_pingInterval); _pingInterval = null; }
}

// ── Avatar helpers ────────────────────────────────────────────────────────────
function getInitials(displayName, email) {
  const name = displayName || email || "U";
  const parts = name.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

const AVATAR_GRADIENTS = [
  "linear-gradient(135deg, #4f46e5, #7c3aed)",
  "linear-gradient(135deg, #0ea5e9, #6366f1)",
  "linear-gradient(135deg, #10b981, #059669)",
  "linear-gradient(135deg, #f59e0b, #ef4444)",
  "linear-gradient(135deg, #ec4899, #8b5cf6)",
];
function pickGradient(str = "") {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_GRADIENTS[Math.abs(hash) % AVATAR_GRADIENTS.length];
}

function clearSupabaseStorage() {
  if (typeof window === "undefined") return;
  Object.keys(window.localStorage)
    .filter((key) => key.startsWith("sb-") || key.includes("supabase"))
    .forEach((key) => window.localStorage.removeItem(key));
}

// ── View Suspense wrapper ─────────────────────────────────────────────────────
function ViewFallback() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, paddingTop: 16 }}>
      {[1,2,3].map(i => <CardSkeleton key={i} />)}
    </div>
  );
}

export default function App() {
  const toast = useToast();
  const [view, setView] = useState("dashboard");
  const [cmdOpen, setCmdOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [moreDrawerOpen, setMoreDrawerOpen] = useState(false);
  const [moreDropdownOpen, setMoreDropdownOpen] = useState(false);
  const [avatarDropdownOpen, setAvatarDropdownOpen] = useState(false);
  const [session, setSession] = useState(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [profileData, setProfileData] = useState(null);
  const touchStart = useRef(null);
  const dropdownRef = useRef(null);
  const avatarDropdownRef = useRef(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setMoreDropdownOpen(false);
      }
      if (avatarDropdownRef.current && !avatarDropdownRef.current.contains(e.target)) {
        setAvatarDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Auth setup
  useEffect(() => {
    if (import.meta.env.VITE_AUTH_PROVIDER === "dev") {
      const saved = localStorage.getItem("dev-session");
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          setSession(parsed);
          setAuthToken(parsed.access_token);
        } catch (e) {
          localStorage.removeItem("dev-session");
        }
      }
      setLoadingAuth(false);
      return;
    }

    supabase.auth.getSession()
      .then(({ data: { session } }) => {
        setSession(session);
        setAuthToken(session?.access_token || null);
      })
      .catch((error) => {
        console.warn("Supabase session restore failed", error);
        clearSupabaseStorage();
        setSession(null);
        setAuthToken(null);
      })
      .finally(() => setLoadingAuth(false));

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "TOKEN_REFRESH_FAILED") {
        clearSupabaseStorage();
        setSession(null);
        setAuthToken(null);
        return;
      }
      setSession(session);
      setAuthToken(session?.access_token || null);
    });

    return () => subscription.unsubscribe();
  }, []);

  // Lazy-load profile for avatar display
  useEffect(() => {
    if (!session) return;
    apiFetch("/profile")
      .then(p => setProfileData(p))
      .catch(() => {});
  }, [session]);

  // Start keep-alive when logged in; stop on logout
  useEffect(() => {
    if (session) startKeepAlive();
    else stopKeepAlive();
    return () => {};
  }, [session]);

  const handleSignOut = async () => {
    stopKeepAlive();
    if (import.meta.env.VITE_AUTH_PROVIDER === "dev") {
      localStorage.removeItem("dev-session");
      setSession(null);
      setAuthToken(null);
      return;
    }
    await supabase.auth.signOut();
  };

  const renderView = () => {
    switch (view) {
      case "dashboard":    return <Dashboard />;
      case "transactions": return <Transactions />;
      case "budgets":      return <Budgets />;
      case "analytics":    return <Analytics />;
      case "accounts":     return <Accounts />;
      case "investments":  return <Investments />;
      case "credit":       return <CreditBenchmarks />;
      case "export":       return <ExportGST />;
      case "audit":        return <AuditWebhooks />;
      case "advisor":      return <Advisor />;
      case "profile":      return <Profile onSignOut={handleSignOut} />;
      default:             return <Dashboard />;
    }
  };

  function handleCmdClose(action) {
    if (action === "toggle") setCmdOpen(p => !p);
    else setCmdOpen(false);
  }

  function navigateBy(delta) {
    const index = ALL_VIEWS.findIndex((item) => item.id === view);
    if (index === -1) return;
    const next = ALL_VIEWS[Math.max(0, Math.min(ALL_VIEWS.length - 1, index + delta))];
    if (next && next.id !== view) setView(next.id);
  }

  function handleTouchStart(e) {
    if (sheetOpen || moreDrawerOpen) return;
    const touch = e.touches[0];
    touchStart.current = { x: touch.clientX, y: touch.clientY };
  }

  function handleTouchEnd(e) {
    if (!touchStart.current) return;
    const touch = e.changedTouches[0];
    const dx = touch.clientX - touchStart.current.x;
    const dy = touch.clientY - touchStart.current.y;
    touchStart.current = null;
    if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.4) {
      navigateBy(dx < 0 ? 1 : -1);
    }
  }

  function navigateTo(id) {
    setView(id);
    setMoreDrawerOpen(false);
    setMoreDropdownOpen(false);
    setAvatarDropdownOpen(false);
  }

  if (loadingAuth) {
    return (
      <div className="app-loading">
        <div className="app-loading-inner">
          <div className="app-loading-logo">
            <LegerLogo size={56} />
          </div>
          <div className="app-loading-name">Ledger</div>
          <Loader2 size={20} className="spin app-loading-spinner" />
        </div>
      </div>
    );
  }

  if (!session) {
    return <Auth />;
  }

  const isSecondaryActive = SECONDARY_VIEWS.some(v => v.id === view) || view === "profile";
  const initials = getInitials(profileData?.display_name, session?.user?.email || profileData?.email);
  const gradient = pickGradient(profileData?.id || session?.user?.id || "");
  const displayName = profileData?.display_name || session?.user?.email?.split("@")[0] || "User";

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="logo" role="banner">
            <LegerLogo size={36} />
            <div>
              <div className="logo-name">Ledger</div>
              <div className="logo-sub">AI Finance Platform</div>
            </div>
          </div>

          {/* Mobile-only: avatar + title in header right */}
          <div className="mobile-header-right">
            <button
              className={`mobile-header-avatar-btn${view === "profile" ? " active" : ""}`}
              onClick={() => navigateTo("profile")}
              aria-label={`Profile — ${displayName}`}
              title={displayName}
            >
              <div className="user-avatar-sm" style={{ background: gradient }}>
                {initials}
              </div>
            </button>
          </div>

          <nav className="nav-tabs" role="tablist" aria-label="Main navigation">
            {PRIMARY_VIEWS.map(({ id, label, Icon }) => (
              <button
                key={id}
                role="tab"
                id={`nav-tab-${id}`}
                className={`nav-tab${view === id ? " active" : ""}`}
                onClick={() => navigateTo(id)}
                aria-selected={view === id}
              >
                <Icon size={15} aria-hidden="true" />
                {label}
              </button>
            ))}

            {/* Desktop More Dropdown */}
            <div style={{ position: "relative" }} ref={dropdownRef}>
              <button
                id="nav-tab-more"
                className={`nav-tab${isSecondaryActive ? " active" : ""}`}
                onClick={() => setMoreDropdownOpen(!moreDropdownOpen)}
                aria-haspopup="true"
                aria-expanded={moreDropdownOpen}
              >
                <MoreHorizontal size={15} /> More
                <ChevronDown size={12} style={{ opacity: 0.5, marginLeft: -4, transition: "transform 0.2s", transform: moreDropdownOpen ? "rotate(180deg)" : "rotate(0deg)" }} />
              </button>
              {moreDropdownOpen && (
                <div className="nav-dropdown" role="menu">
                  {SECONDARY_VIEWS.map(({ id, label, Icon }) => (
                    <button
                      key={id}
                      role="menuitem"
                      className={`nav-dropdown-item${view === id ? " active" : ""}`}
                      onClick={() => navigateTo(id)}
                    >
                      <Icon size={14} aria-hidden="true" /> {label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="nav-divider" aria-hidden="true" />

            {/* Cmd Palette button */}
            <button
              className="nav-tab cmd-k-btn"
              onClick={() => setCmdOpen(true)}
              title="Command palette (Ctrl+K)"
              aria-label="Open command palette"
            >
              <Command size={14} />
              <kbd className="cmd-kbd">⌘K</kbd>
            </button>

            {/* Avatar dropdown */}
            <div style={{ position: "relative" }} ref={avatarDropdownRef}>
              <button
                className="user-avatar-btn"
                onClick={() => setAvatarDropdownOpen(!avatarDropdownOpen)}
                aria-label={`Account menu for ${displayName}`}
                aria-haspopup="true"
                aria-expanded={avatarDropdownOpen}
                title={displayName}
              >
                <div className="user-avatar-sm" style={{ background: gradient }}>
                  {initials}
                </div>
                <ChevronDown size={12} className="avatar-chevron" style={{ transform: avatarDropdownOpen ? "rotate(180deg)" : "rotate(0deg)" }} />
              </button>
              {avatarDropdownOpen && (
                <div className="avatar-dropdown" role="menu">
                  <div className="avatar-dropdown-header">
                    <div className="user-avatar-md" style={{ background: gradient }}>{initials}</div>
                    <div>
                      <div className="avatar-dropdown-name">{displayName}</div>
                      <div className="avatar-dropdown-email">{session?.user?.email || profileData?.email}</div>
                    </div>
                  </div>
                  <div className="avatar-dropdown-divider" />
                  <button className="avatar-dropdown-item" role="menuitem" onClick={() => navigateTo("profile")}>
                    <User size={14} /> My Profile
                  </button>
                  <div className="avatar-dropdown-divider" />
                  <button className="avatar-dropdown-item danger" role="menuitem" onClick={handleSignOut}>
                    <LogOut size={14} /> Sign Out
                  </button>
                </div>
              )}
            </div>
          </nav>
        </div>
      </header>

      <main
        className="page-content swipe-shell"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        <Suspense fallback={<ViewFallback />}>
          <div key={view} className="swipe-view">{renderView()}</div>
        </Suspense>
      </main>

      {/* Desktop FAB — hidden on mobile (mobile has center Add button) */}
      <button className="quick-add-fab" onClick={() => setSheetOpen(true)} aria-label="Add transaction">
        <Plus size={24} />
      </button>

      {/* Mobile Bottom Nav */}
      <nav className="mobile-bottom-nav" aria-label="Primary mobile navigation">
        <button
          className={`mobile-nav-item${view === "dashboard" ? " active" : ""}`}
          onClick={() => navigateTo("dashboard")}
          aria-label="Dashboard"
        >
          <LayoutDashboard size={20} aria-hidden="true" />
          <span>Dashboard</span>
        </button>
        <button
          className={`mobile-nav-item${view === "budgets" ? " active" : ""}`}
          onClick={() => navigateTo("budgets")}
          aria-label="Budgets"
        >
          <Target size={20} aria-hidden="true" />
          <span>Budgets</span>
        </button>

        {/* Center Add button */}
        <button
          className="mobile-nav-item center-add-btn"
          onClick={() => setSheetOpen(true)}
          aria-label="Add transaction"
        >
          <div className="center-add-icon-wrap">
            <Plus size={24} aria-hidden="true" />
          </div>
          <span>Add</span>
        </button>

        <button
          className={`mobile-nav-item${view === "investments" ? " active" : ""}`}
          onClick={() => navigateTo("investments")}
          aria-label="Investments"
        >
          <Briefcase size={20} aria-hidden="true" />
          <span>Invest</span>
        </button>

        <button
          className={`mobile-nav-item${isSecondaryActive || view === "advisor" || view === "credit" || view === "transactions" ? " active" : ""}`}
          onClick={() => setMoreDrawerOpen(true)}
          aria-label="More options"
        >
          <Grid size={20} aria-hidden="true" />
          <span>More</span>
        </button>
      </nav>

      {/* Mobile More Drawer */}
      <div className={`sheet-backdrop${moreDrawerOpen ? " open" : ""}`} onClick={() => setMoreDrawerOpen(false)} />
      <div className={`bottom-sheet${moreDrawerOpen ? " open" : ""}`} role="dialog" aria-modal="true" aria-label="All features">
        <div className="sheet-handle" />

        {/* User info in drawer */}
        <div className="drawer-user-info">
          <div className="user-avatar-sm" style={{ background: gradient, width: 40, height: 40, fontSize: 15 }}>{initials}</div>
          <div>
            <div className="drawer-user-name">{displayName}</div>
            <div className="drawer-user-email">{session?.user?.email || profileData?.email}</div>
          </div>
        </div>

        <div className="sheet-header" style={{ marginTop: 0 }}>
          <div className="form-section-title" style={{ marginBottom: 0 }}>All Features</div>
          <button className="icon-btn" onClick={() => setMoreDrawerOpen(false)} aria-label="Close menu">
            <X size={18} />
          </button>
        </div>

        <div className="drawer-grid">
          {ALL_VIEWS.map(({ id, label, Icon }) => (
            <button
              key={id}
              className={`type-btn${view === id ? " active" : ""}`}
              style={{ justifyContent: "flex-start", padding: "14px 16px" }}
              onClick={() => navigateTo(id)}
            >
              <Icon size={17} className={view === id ? "icon-accent" : ""} /> {label}
            </button>
          ))}
          <button
            className={`type-btn${view === "profile" ? " active" : ""}`}
            style={{ justifyContent: "flex-start", padding: "14px 16px" }}
            onClick={() => navigateTo("profile")}
          >
            <User size={17} className={view === "profile" ? "icon-accent" : ""} /> Profile
          </button>
        </div>

        <button
          className="btn-secondary full-width"
          onClick={handleSignOut}
          style={{ color: "var(--negative)", borderColor: "#fecdd3", marginTop: 8 }}
        >
          <LogOut size={16} /> Sign Out
        </button>
      </div>

      <QuickAddSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        onSaved={() => {
          toast("Transaction added ✓", "success");
          if (view !== "transactions") setView("transactions");
        }}
      />
      <CommandPalette open={cmdOpen} onClose={handleCmdClose} onNavigate={navigateTo} />
    </div>
  );
}

// ── Quick Add Sheet ───────────────────────────────────────────────────────────
function QuickAddSheet({ open, onClose, onSaved }) {
  const toast = useToast();
  const [submitting, setSubmitting] = React.useState(false);
  const [form, setForm] = React.useState({
    type: "expense", amount: "", category: "Groceries",
    description: "", date: today(), source: "cash",
  });

  // Reset form when opened
  useEffect(() => {
    if (open) setForm({ type: "expense", amount: "", category: "Groceries", description: "", date: today(), source: "cash" });
  }, [open]);

  async function save(e) {
    e.preventDefault();
    if (!form.amount || Number(form.amount) <= 0) return toast("Enter a valid amount", "error");
    setSubmitting(true);
    try {
      await apiFetch("/transactions", {
        method: "POST",
        body: JSON.stringify({ ...form, amount: Number(form.amount) }),
      });
      onSaved();
      onClose();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className={`sheet-backdrop${open ? " open" : ""}`} onClick={onClose} />
      <section className={`bottom-sheet${open ? " open" : ""}`} aria-hidden={!open} aria-modal="true" role="dialog" aria-label="Add Transaction">
        <div className="sheet-handle" />
        <div className="sheet-header">
          <div className="form-section-title" style={{ marginBottom: 0 }}>Add Transaction</div>
          <button className="icon-btn" onClick={onClose} aria-label="Close quick transaction">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={save}>
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

          <div className="form-field quick-amount-field">
            <label className="form-label" style={{ textAlign: "center", fontSize: 13, color: "var(--text-secondary)" }}>Amount</label>
            <div className="quick-amount-row">
              <span className="quick-amount-symbol">₹</span>
              <input
                required
                autoFocus={open}
                type="number"
                min="1"
                step="0.01"
                value={form.amount}
                placeholder="0.00"
                className="quick-amount-input"
                inputMode="decimal"
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </div>
            <div className="quick-amount-underline" />
          </div>

          <div className="form-grid-2">
            <div className="form-field">
              <label className="form-label">Category</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {(form.type === "income" ? ["Salary", "Freelance", "Other"] : EXPENSE_CATEGORIES).map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">Date</label>
              <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </div>
          </div>

          <div className="form-field" style={{ marginBottom: 32 }}>
            <label className="form-label">Description</label>
            <input
              required
              placeholder="What was this for?"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>

          <button className="btn-primary full-width" disabled={submitting} style={{ padding: "16px" }}>
            {submitting ? <><Loader2 size={16} className="spin" /> Saving…</> : "Save Transaction"}
          </button>
        </form>
      </section>
    </>
  );
}
