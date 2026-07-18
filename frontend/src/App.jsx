import React, { useState, useEffect, lazy, Suspense } from "react";
import { Routes, Route, Navigate, useLocation, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { loadPersistedCredential, clearCredential, onAuthChange, parseIdToken } from "./google-auth";
import { apiFetch, API_BASE, EXPENSE_CATEGORIES, setAuthToken, today, KEYS } from "./lib";
import { useToast, LedgerLogo, CardSkeleton } from "./components/ui";
import Auth from "./views/Auth";
import CommandPalette from "./components/CommandPalette";
import ColdStart from "./components/ColdStart";

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
  Wallet, Download, Shield, Briefcase, Gauge, LogOut,
  Loader2, X, Grid, User,
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

const VIEW_IDS = new Set([...ALL_VIEWS.map((v) => v.id), "profile"]);
const viewPath = (id) => (id === "dashboard" ? "/" : `/${id}`);

// Legacy PWA manifest shortcuts / deep links used `/?view=X`. Redirect them
// to the real route so refresh and back/forward work the same everywhere.
function LegacyViewRedirect() {
  const requested = new URLSearchParams(window.location.search).get("view");
  if (requested && VIEW_IDS.has(requested)) {
    return <Navigate to={viewPath(requested)} replace />;
  }
  return <Dashboard />;
}

export default function App() {
  const toast = useToast();
  const location = useLocation();
  const navigate = useNavigate();
  const view = location.pathname === "/" ? "dashboard" : location.pathname.slice(1).split("/")[0];
  const [cmdOpen, setCmdOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [moreDrawerOpen, setMoreDrawerOpen] = useState(false);
  const [session, setSession] = useState(null);
  const [loadingAuth, setLoadingAuth] = useState(true);

  // Swipe navigation state
  const [touchStart, setTouchStart] = useState(null);
  const [touchEnd, setTouchEnd] = useState(null);

  // Auth setup — Google credential as session token
  useEffect(() => {
    const credential = loadPersistedCredential();
    if (credential) {
      setSession({ credential });
      setAuthToken(credential);
    }
    setLoadingAuth(false);

    const unsubscribe = onAuthChange((credential) => {
      if (credential) {
        setSession({ credential });
        setAuthToken(credential);
      } else {
        setSession(null);
        setAuthToken(null);
      }
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!session) return;
    // Fire a warm-up ping immediately so the free-tier backend starts waking
    // before the first real (data-bearing) request needs it.
    fetch(`${API_BASE}/ping`).catch(() => {});
  }, [session]);

  // Shared with the Profile view's own useQuery(KEYS.profile()) call — same
  // cache entry, so switching to Profile shows data instantly.
  const { data: profileData } = useQuery({
    queryKey: KEYS.profile(),
    queryFn: () => apiFetch("/profile"),
    enabled: !!session,
  });

  useEffect(() => {
    if (session) startKeepAlive(); else stopKeepAlive();
  }, [session]);

  // Close more drawer on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") { setMoreDrawerOpen(false); setSheetOpen(false); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const handleSignOut = () => {
    stopKeepAlive();
    clearCredential();
  };

  function navigateTo(id) {
    navigate(viewPath(id));
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
    const minSwipeDistance = 50;
    const isLeftSwipe = distance > minSwipeDistance;
    const isRightSwipe = distance < -minSwipeDistance;

    if (isLeftSwipe || isRightSwipe) {
      const viewsList = ALL_VIEWS.map(v => v.id).concat(["profile"]);
      const currentIndex = viewsList.indexOf(view);
      
      if (currentIndex !== -1) {
        if (isLeftSwipe && currentIndex < viewsList.length - 1) {
          navigateTo(viewsList[currentIndex + 1]);
        }
        if (isRightSwipe && currentIndex > 0) {
          navigateTo(viewsList[currentIndex - 1]);
        }
      }
    }
  };

  if (loadingAuth) {
    return (
      <div className="app-loading">
        <ColdStart />
        <div className="app-loading-inner">
          <LedgerLogo size={64} />
          <Loader2 size={24} className="spin" style={{ color: "var(--primary)" }} />
        </div>
      </div>
    );
  }

  if (!session) return (<><ColdStart /><Auth /></>);

  const googleUser = session?.credential ? parseIdToken(session.credential) : null;
  const userEmail = profileData?.email || googleUser?.email || null;
  const userId = profileData?.id || googleUser?.sub || "";
  const initials = getInitials(profileData?.display_name, userEmail);
  const gradient = pickGradient(userId);
  const displayName = profileData?.display_name || googleUser?.name || userEmail?.split("@")[0] || "User";
  const avatarUrl = profileData?.avatar_url || googleUser?.picture;

  return (
    <div className="app">
      <ColdStart />
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
              <LedgerLogo size={30} />
              <span className="sidebar-logo-name" style={{ fontSize: 20 }}>Ledger</span>
            </div>
            <button
              onClick={() => navigateTo("profile")}
              style={{ border: "none", cursor: "pointer", background: "none" }}
              aria-label="Profile"
            >
              <div style={{
                width: 36, height: 36, borderRadius: 10, background: gradient,
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "white", fontWeight: 700, fontSize: 14,
                overflow: "hidden",
              }}>
                {avatarUrl ? <img src={avatarUrl} alt="Avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials}
              </div>
            </button>
          </div>
        </header>

        <main className="page-content fade-in" id="main-content">
          <Suspense fallback={<ViewFallback />}>
            <Routes>
              <Route path="/" element={<LegacyViewRedirect />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/budgets" element={<Budgets />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/investments" element={<Investments />} />
              <Route path="/credit" element={<CreditBenchmarks />} />
              <Route path="/export" element={<ExportGST />} />
              <Route path="/audit" element={<AuditWebhooks />} />
              <Route path="/advisor" element={<Advisor />} />
              <Route path="/profile" element={<Profile onSignOut={handleSignOut} />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
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
        <button className={`mobile-nav-item${view === "dashboard" ? " active" : ""}`} onClick={() => navigateTo("dashboard")} aria-label="Dashboard">
          <LayoutDashboard size={20} aria-hidden="true" />
          <span>Home</span>
        </button>
        <button className={`mobile-nav-item${view === "budgets" ? " active" : ""}`} onClick={() => navigateTo("budgets")} aria-label="Budgets">
          <Target size={20} aria-hidden="true" />
          <span>Budgets</span>
        </button>
        <button className="mobile-nav-item center-add-btn" onClick={() => setSheetOpen(true)} aria-label="Add transaction">
          <div className="center-add-icon-wrap">
            <Plus size={22} aria-hidden="true" />
          </div>
          <span>Add</span>
        </button>
        <button className={`mobile-nav-item${view === "investments" ? " active" : ""}`} onClick={() => navigateTo("investments")} aria-label="Investments">
          <Briefcase size={20} aria-hidden="true" />
          <span>Invest</span>
        </button>
        <button
          className={`mobile-nav-item${moreDrawerOpen ? " active" : ""}`}
          onClick={() => setMoreDrawerOpen(true)}
          aria-label="More features"
        >
          <Grid size={20} aria-hidden="true" />
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
        <div className="drawer-user-info">
          <div style={{
            width: 40, height: 40, borderRadius: 12, background: gradient,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "white", fontWeight: 700, fontSize: 15, flexShrink: 0,
            overflow: "hidden",
          }}>
            {avatarUrl ? <img src={avatarUrl} alt="Avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials}
          </div>
          <div>
            <div className="drawer-user-name">{displayName}</div>
            <div className="drawer-user-email">{userEmail}</div>
          </div>
        </div>
        <div className="form-section-title" style={{ marginBottom: 16 }}>All Features</div>
        <div className="drawer-grid">
          {ALL_VIEWS.map(({ id, label, Icon }) => (
            <button
              key={id}
              className={`type-btn${view === id ? " active" : ""}`}
              style={{ justifyContent: "flex-start", padding: "12px 14px", borderRadius: 12 }}
              onClick={() => navigateTo(id)}
            >
              <Icon size={16} aria-hidden="true" /> {label}
            </button>
          ))}
          <button
            className={`type-btn${view === "profile" ? " active" : ""}`}
            style={{ justifyContent: "flex-start", padding: "12px 14px", borderRadius: 12 }}
            onClick={() => navigateTo("profile")}
          >
            <User size={16} aria-hidden="true" /> Profile
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
  const [submitting, setSubmitting] = React.useState(false);
  const [form, setForm] = React.useState({
    type: "expense", amount: "", category: "Groceries",
    description: "", date: today(), source: "cash",
  });

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
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className={`sheet-backdrop${open ? " open" : ""}`} onClick={onClose} aria-hidden="true" />
      <section
        className={`bottom-sheet${open ? " open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="Add Transaction"
        aria-hidden={!open}
      >
        <div className="sheet-handle" />
        <div className="sheet-header">
          <div className="form-section-title" style={{ marginBottom: 0 }}>Add Transaction</div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={save}>
          {/* Type Toggle */}
          <div className="type-toggle">
            <button
              type="button"
              className={`type-btn${form.type === "expense" ? " active expense" : ""}`}
              onClick={() => setForm({ ...form, type: "expense", category: "Groceries" })}
            >
              Expense
            </button>
            <button
              type="button"
              className={`type-btn${form.type === "income" ? " active income" : ""}`}
              onClick={() => setForm({ ...form, type: "income", category: "Salary" })}
            >
              Income
            </button>
          </div>

          {/* Amount */}
          <div className="form-field quick-amount-field">
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

          {/* Category + Date */}
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

          {/* Description */}
          <div className="form-field" style={{ marginBottom: 28 }}>
            <label className="form-label">Description</label>
            <input
              required
              placeholder="What was this for?"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>

          <button className="btn-primary full-width" disabled={submitting} style={{ padding: "16px", justifyContent: "center" }}>
            {submitting ? <><Loader2 size={16} className="spin" /> Saving…</> : "Save Transaction"}
          </button>
        </form>
      </section>
    </>
  );
}
