import React, { useState, useEffect, useCallback, useRef } from "react";
import { API_BASE, apiFetch, authHeaders, money, setCurrencyPreference, setDisplayRates, setRegionPreference } from "../lib";
import { useToast } from "../components/ui";
import {
  User, Mail, Calendar, TrendingUp, TrendingDown,
  DollarSign, CreditCard, Target, Edit3, Check, X,
  LogOut, AlertTriangle, Shield, Wallet, BarChart3,
  Loader2, RefreshCw, Camera, Download, Trash2
} from "lucide-react";

// ── Avatar helpers ────────────────────────────────────────────────────────────
function getInitials(displayName, email) {
  const name = displayName || email || "U";
  const parts = name.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

const AVATAR_GRADIENTS = [
  "linear-gradient(135deg, var(--primary), var(--info))",
  "linear-gradient(135deg, var(--info), var(--negative))",
  "linear-gradient(135deg, var(--primary), var(--warning))",
  "linear-gradient(135deg, var(--warning), var(--negative))",
  "linear-gradient(135deg, var(--negative), var(--info))",
];
const REGION_OPTIONS = [["IN", "India"], ["US", "United States"], ["GB", "United Kingdom"], ["CA", "Canada"], ["AU", "Australia"], ["SG", "Singapore"], ["AE", "United Arab Emirates"], ["JP", "Japan"], ["CH", "Switzerland"], ["CN", "China"], ["HK", "Hong Kong"], ["OTHER", "Other"]];

function pickGradient(str = "") {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_GRADIENTS[Math.abs(hash) % AVATAR_GRADIENTS.length];
}

function formatDate(isoStr) {
  if (!isoStr) return "—";
  return new Date(isoStr).toLocaleDateString("en-IN", {
    year: "numeric", month: "long", day: "numeric",
  });
}

// ── Main Profile component ────────────────────────────────────────────────────
export default function Profile({ onSignOut }) {
  const toast = useToast();
  const fileInputRef = useRef(null);
  const [profile, setProfile] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const [form, setForm] = useState({ display_name: "", currency_preference: "INR", region: "IN", income_pattern: "not_sure", pay_cycle: "monthly", risk_comfort: "not_sure", household_mode: "individual", recurring_tolerance: "standard", cloud_ai_enabled: true, insight_frequency: "daily", quiet_hours_start: 22, quiet_hours_end: 7, proactive_daily_cap: 3 });
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [exportingData, setExportingData] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deletingData, setDeletingData] = useState(false);
  const [customCategories, setCustomCategories] = useState([]);
  const [merchantAliases, setMerchantAliases] = useState([]);
  const [categoryName, setCategoryName] = useState("");
  const [aliasForm, setAliasForm] = useState({ alias: "", canonical: "" });

  const loadProfile = useCallback(async () => {
    setLoading(true);
    try {
      const [p, s, categories, aliases] = await Promise.all([
        apiFetch("/profile"),
        apiFetch("/profile/stats"),
        apiFetch("/categories"),
        apiFetch("/merchant-aliases"),
      ]);
      setProfile(p);
      setCurrencyPreference(p.currency_preference);
      setRegionPreference(p.region);
      setStats(s);
      setCustomCategories((categories || []).filter((item) => item.is_custom));
      setMerchantAliases(aliases || []);
      setForm({ display_name: p.display_name || "", currency_preference: p.currency_preference || "INR", region: p.region || "IN", income_pattern: p.income_pattern || "not_sure", pay_cycle: p.pay_cycle || "monthly", risk_comfort: p.risk_comfort || "not_sure", household_mode: p.household_mode || "individual", recurring_tolerance: p.recurring_tolerance || "standard", cloud_ai_enabled: p.cloud_ai_enabled !== false, insight_frequency: p.insight_frequency || "daily", quiet_hours_start: p.quiet_hours_start ?? 22, quiet_hours_end: p.quiet_hours_end ?? 7, proactive_daily_cap: p.proactive_daily_cap ?? 3 });
    } catch (e) {
      if (e.message?.startsWith("Currency cannot be changed")) {
        // Do not leave a rejected currency in the form: subsequent saves would
        // resend the same unsafe relabel request and produce repeated 409s.
        setForm(current => ({
          ...current,
          currency_preference: profile?.currency_preference || current.currency_preference,
        }));
      }
      toast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const addCategory = async () => {
    if (!categoryName.trim()) return;
    try {
      const category = await apiFetch("/categories", { method: "POST", body: JSON.stringify({ name: categoryName.trim(), kind: "expense", reporting_group: "Other" }) });
      setCustomCategories((items) => [...items, category]);
      setCategoryName("");
      toast("Category added", "success");
    } catch (e) { toast(e.message, "error"); }
  };

  const addAlias = async () => {
    if (!aliasForm.alias.trim() || !aliasForm.canonical.trim()) return;
    try {
      const alias = await apiFetch("/merchant-aliases", { method: "POST", body: JSON.stringify(aliasForm) });
      setMerchantAliases((items) => [...items.filter((item) => item.id !== alias.id), alias]);
      setAliasForm({ alias: "", canonical: "" });
      toast("Merchant alias saved", "success");
    } catch (e) { toast(e.message, "error"); }
  };

  const removeAlias = async (id) => {
    try { await apiFetch(`/merchant-aliases/${id}`, { method: "DELETE" }); setMerchantAliases((items) => items.filter((item) => item.id !== id)); }
    catch (e) { toast(e.message, "error"); }
  };

  useEffect(() => { loadProfile(); }, [loadProfile]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await apiFetch("/profile", {
        method: "PUT",
        body: JSON.stringify({
          display_name: form.display_name.trim() || null,
          currency_preference: form.currency_preference,
          region: form.region,
          income_pattern: form.income_pattern,
          pay_cycle: form.pay_cycle,
          risk_comfort: form.risk_comfort,
          household_mode: form.household_mode,
          recurring_tolerance: form.recurring_tolerance,
          cloud_ai_enabled: form.cloud_ai_enabled,
          insight_frequency: form.insight_frequency,
          quiet_hours_start: Number(form.quiet_hours_start),
          quiet_hours_end: Number(form.quiet_hours_end),
          proactive_daily_cap: Number(form.proactive_daily_cap),
        }),
      });
      setProfile(updated);
      setCurrencyPreference(updated.currency_preference);
      setRegionPreference(updated.region);
      const recordCurrency = localStorage.getItem("ledger-record-currency") || updated.currency_preference;
      localStorage.setItem("ledger-record-currency", recordCurrency);
      apiFetch(`/currency/rates?base=${recordCurrency}`)
        .then((rates) => setDisplayRates(rates.base, rates.rates, rates.date))
        .catch(() => {});
      setEditing(false);
      toast("Profile updated", "success");
    } catch (e) {
      if (e.message?.startsWith("Currency cannot be changed")) {
        // Restore the persisted currency so a later save does not resend the
        // rejected relabel request and produce another 409.
        setForm(current => ({
          ...current,
          currency_preference: profile?.currency_preference || current.currency_preference,
        }));
      }
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setForm({ display_name: profile?.display_name || "", currency_preference: profile?.currency_preference || "INR", region: profile?.region || "IN", income_pattern: profile?.income_pattern || "not_sure", pay_cycle: profile?.pay_cycle || "monthly", risk_comfort: profile?.risk_comfort || "not_sure", household_mode: profile?.household_mode || "individual", recurring_tolerance: profile?.recurring_tolerance || "standard", cloud_ai_enabled: profile?.cloud_ai_enabled !== false, insight_frequency: profile?.insight_frequency || "daily", quiet_hours_start: profile?.quiet_hours_start ?? 22, quiet_hours_end: profile?.quiet_hours_end ?? 7, proactive_daily_cap: profile?.proactive_daily_cap ?? 3 });
    setEditing(false);
  };

  const handleFullExport = async () => {
    setExportingData(true);
    try {
      const res = await fetch(`${API_BASE}/export/full`, { headers: authHeaders() });
      if (!res.ok) throw new Error("Could not prepare your data export");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ledger_full_export.json";
      link.click();
      URL.revokeObjectURL(url);
      toast("Full data export downloaded", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setExportingData(false);
    }
  };

  const handleDeleteData = async () => {
    if (deleteConfirmation !== "DELETE") return;
    setDeletingData(true);
    try {
      await apiFetch("/profile/data", {
        method: "DELETE",
        body: JSON.stringify({ confirmation: deleteConfirmation }),
      });
      toast("Your Ledger data was permanently deleted", "success");
      onSignOut();
    } catch (e) {
      toast(e.message, "error");
      setDeletingData(false);
    }
  };

  const handleAvatarClick = () => {
    if (fileInputRef.current) fileInputRef.current.click();
  };

  const handleAvatarChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast("Please select an image file", "error");
      return;
    }
    
    if (file.size > 2 * 1024 * 1024) {
      toast("Image must be smaller than 2MB", "error");
      return;
    }

    setUploadingAvatar(true);
    try {
      // Convert to base64
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = async () => {
        const base64Str = reader.result;
        
        const updated = await apiFetch("/profile", {
          method: "PUT",
          body: JSON.stringify({
            avatar_url: base64Str,
          }),
        });
        setProfile(updated);
        toast("Profile photo updated", "success");
        setUploadingAvatar(false);
      };
      reader.onerror = () => {
        toast("Failed to read file", "error");
        setUploadingAvatar(false);
      };
    } catch (err) {
      toast(err.message, "error");
      setUploadingAvatar(false);
    }
    // reset input
    e.target.value = null;
  };

  if (loading) {
    return (
      <div className="view-profile">
        <div className="profile-skeleton">
          <div className="profile-skeleton-avatar" />
          <div className="profile-skeleton-lines">
            <div className="skeleton-line wide" />
            <div className="skeleton-line medium" />
            <div className="skeleton-line narrow" />
          </div>
        </div>
        <div className="profile-stats-grid">
          {[1,2,3,4,5,6].map(i => (
            <div key={i} className="card profile-stat-card skeleton-card">
              <div className="skeleton-line narrow" style={{ marginBottom: 12 }} />
              <div className="skeleton-line wide" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const displayName = profile?.display_name || profile?.email?.split("@")[0] || "User";
  const initials = getInitials(profile?.display_name, profile?.email);
  const gradient = pickGradient(profile?.id || "");
  const avatarUrl = profile?.avatar_url;

  const statCards = [
    {
      icon: BarChart3, label: "Transactions", value: stats?.total_transactions ?? "—",
      isCount: true, color: "var(--info)", bg: "rgba(56,189,248,0.16)",
    },
    {
      icon: TrendingUp, label: "Total Income", value: money(stats?.total_income || 0),
      color: "var(--positive)", bg: "var(--positive-soft)",
    },
    {
      icon: TrendingDown, label: "Total Expenses", value: money(stats?.total_expenses || 0),
      color: "var(--negative)", bg: "var(--negative-soft)",
    },
    {
      icon: DollarSign, label: "Net Balance", value: money(stats?.net_balance || 0),
      color: Number(stats?.net_balance || 0) >= 0 ? "var(--positive)" : "var(--negative)",
      bg: Number(stats?.net_balance || 0) >= 0 ? "var(--positive-soft)" : "var(--negative-soft)",
    },
    {
      icon: Wallet, label: "Accounts", value: stats?.accounts_count ?? "—",
      isCount: true, color: "var(--info)", bg: "rgba(56,189,248,0.12)",
    },
    {
      icon: Target, label: "Budgets", value: stats?.budgets_count ?? "—",
      isCount: true, color: "var(--warning)", bg: "rgba(250,204,21,0.16)",
    },
  ];

  return (
    <div className="view-profile premium-view">
      {/* ── Profile Hero ─────────────────────────────────────────────── */}
      <div className="profile-hero card premium-hero">
        <div className="profile-avatar-wrap" onClick={handleAvatarClick} style={{ cursor: "pointer" }}>
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleAvatarChange} 
            accept="image/*" 
            style={{ display: "none" }} 
          />
          {avatarUrl ? (
            <img src={avatarUrl} alt="Avatar" className="profile-avatar-lg" />
          ) : (
            <div
              className="profile-avatar-lg"
              style={{ background: gradient }}
              aria-label={`Avatar for ${displayName}`}
            >
              {initials}
            </div>
          )}
          
          <div className="profile-avatar-overlay-hover">
            <Camera size={24} color="#fff" />
          </div>

          {uploadingAvatar && (
            <div className="profile-avatar-overlay">
              <Loader2 className="spin" size={24} color="#fff" />
            </div>
          )}
          <div className="profile-avatar-badge">
            <Shield size={12} />
          </div>
        </div>

        <div className="profile-hero-info">
          {editing ? (
            <div className="profile-edit-inline fade-in">
              <input
                autoFocus
                className="profile-name-input premium-input"
                value={form.display_name}
                onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
                placeholder="Your display name"
                maxLength={128}
                onKeyDown={e => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") handleCancelEdit(); }}
              />
              <div className="profile-edit-actions">
                <button
                  className="profile-edit-confirm"
                  onClick={handleSave}
                  disabled={saving}
                  aria-label="Save name"
                >
                  {saving ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
                </button>
                <button
                  className="profile-edit-cancel"
                  onClick={handleCancelEdit}
                  disabled={saving}
                  aria-label="Cancel"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          ) : (
            <div className="profile-name-row fade-in">
              <h1 className="profile-name premium-title">{displayName}</h1>
              <button
                className="profile-edit-btn"
                onClick={() => setEditing(true)}
                aria-label="Edit display name"
              >
                <Edit3 size={14} />
              </button>
            </div>
          )}

          <div className="profile-meta">
            {profile?.email && (
              <span className="profile-meta-item">
                <Mail size={13} /> {profile.email}
              </span>
            )}
            <span className="profile-meta-item">
              <Calendar size={13} /> Joined {formatDate(profile?.created_at)}
            </span>
          </div>
        </div>

        <button
          className="profile-refresh-btn premium-icon-btn"
          onClick={loadProfile}
          aria-label="Refresh profile"
          title="Refresh"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      {/* ── Stats Grid ───────────────────────────────────────────────── */}
      <div className="profile-stats-grid">
        {statCards.map(({ icon: Icon, label, value, isCount, color, bg }) => (
          <div
            key={label}
            className="card profile-stat-card"
            style={{ "--stat-accent": color }}
          >
            <div className="profile-stat-icon" style={{ background: bg, color }}>
              <Icon size={18} />
            </div>
            <div className="profile-stat-value" style={{ color }}>
              {isCount ? (value === "—" ? "—" : Number(value).toLocaleString("en-IN")) : value}
            </div>
            <div className="profile-stat-label">{label}</div>
          </div>
        ))}
      </div>


      {/* ── Combined Settings Section ─────────────────────────────────── */}
      <div className="card profile-settings-card premium-settings">
        <div className="settings-section">
          <h2 className="settings-title">
            <CreditCard size={18} /> Preferences
          </h2>
          <div className="settings-list">
            <div className="settings-item">
              <div className="settings-item-info">
                <span className="settings-item-label">Currency</span>
                <span className="settings-item-desc">Choose the currency used to display your balances, totals, and analysis. Historical records stay in their original currency and are converted using a dated reference rate.</span>
              </div>
              <div className="settings-item-action">
                <select
                  className="premium-select"
                  value={form.currency_preference}
                  onChange={e => setForm(f => ({ ...f, currency_preference: e.target.value }))}
                >
                  <option value="INR">🇮🇳 INR — Indian Rupee</option>
                  <option value="USD">🇺🇸 USD — US Dollar</option>
                  <option value="EUR">🇪🇺 EUR — Euro</option>
                  <option value="GBP">🇬🇧 GBP — British Pound</option>
                  <option value="AED">🇦🇪 AED — UAE Dirham</option>
                  <option value="SGD">🇸🇬 SGD — Singapore Dollar</option>
                  <option value="CAD">🇨🇦 CAD — Canadian Dollar</option>
                  <option value="AUD">🇦🇺 AUD — Australian Dollar</option>
                  <option value="JPY">🇯🇵 JPY — Japanese Yen</option>
                  <option value="CHF">🇨🇭 CHF — Swiss Franc</option>
                  <option value="CNY">🇨🇳 CNY — Chinese Yuan</option>
                  <option value="HKD">🇭🇰 HKD — Hong Kong Dollar</option>
                </select>
              </div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Country or region</span><span className="settings-item-desc">Used for number formatting</span></div>
              <div className="settings-item-action"><select className="premium-select" value={form.region} onChange={(e) => setForm((value) => ({ ...value, region: e.target.value }))}>{REGION_OPTIONS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Income pattern</span><span className="settings-item-desc">A self-reported preference; does not change forecasts</span></div>
              <div className="settings-item-action"><select className="premium-select" value={form.income_pattern} onChange={(e) => setForm((value) => ({ ...value, income_pattern: e.target.value }))}><option value="regular">Mostly regular</option><option value="irregular">Irregular or freelance</option><option value="mixed">A mix of regular and variable</option><option value="not_sure">Not sure yet</option></select></div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Pay cycle</span><span className="settings-item-desc">A self-reported rhythm used to make planning language more relevant; Ledger does not infer payday.</span></div>
              <div className="settings-item-action"><select className="premium-select" value={form.pay_cycle} onChange={(e) => setForm((value) => ({ ...value, pay_cycle: e.target.value }))} aria-label="Pay cycle"><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option><option value="irregular">Irregular</option></select></div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Risk comfort</span><span className="settings-item-desc">Only a stated preference. It is not a risk score or investment recommendation.</span></div>
              <div className="settings-item-action"><select className="premium-select" value={form.risk_comfort} onChange={(e) => setForm((value) => ({ ...value, risk_comfort: e.target.value }))} aria-label="Risk comfort"><option value="not_sure">Not sure yet</option><option value="conservative">Prefer lower volatility</option><option value="balanced">Balanced</option><option value="aggressive">Comfortable with volatility</option></select></div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Household view</span><span className="settings-item-desc">Choose whether your Ledger records represent only you or shared household spending.</span></div>
              <div className="settings-item-action"><select className="premium-select" value={form.household_mode} onChange={(e) => setForm((value) => ({ ...value, household_mode: e.target.value }))} aria-label="Household view"><option value="individual">Just me</option><option value="shared">Shared household</option></select></div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Recurring detection tolerance</span><span className="settings-item-desc">How much variation Ledger should tolerate when suggesting recurring payments; suggestions still require confirmation.</span></div>
              <div className="settings-item-action"><select className="premium-select" value={form.recurring_tolerance} onChange={(e) => setForm((value) => ({ ...value, recurring_tolerance: e.target.value }))} aria-label="Recurring detection tolerance"><option value="strict">Strict</option><option value="standard">Standard</option><option value="flexible">Flexible</option></select></div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info">
                <span className="settings-item-label">Cloud AI explanations</span>
                <span className="settings-item-desc">When enabled, Ledger may send a minimized financial context to a configured cloud provider for explanations and planning. Direct factual answers still run locally.</span>
              </div>
              <div className="settings-item-action">
                <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-secondary)" }}>
                  <input
                    type="checkbox"
                    checked={form.cloud_ai_enabled}
                    onChange={(e) => setForm((value) => ({ ...value, cloud_ai_enabled: e.target.checked }))}
                    aria-label="Enable cloud AI explanations"
                  />
                  {form.cloud_ai_enabled ? "Enabled" : "Disabled"}
                </label>
              </div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info">
                <span className="settings-item-label">Insight frequency</span>
                <span className="settings-item-desc">Choose whether Ledger shows all proactive observations, only important ones, or none.</span>
              </div>
              <div className="settings-item-action">
                <select
                  className="premium-select"
                  value={form.insight_frequency}
                  onChange={(e) => setForm((value) => ({ ...value, insight_frequency: e.target.value }))}
                  aria-label="Insight frequency"
                >
                  <option value="off">Off</option>
                  <option value="important">Important only</option>
                  <option value="daily">All available</option>
                  <option value="weekly">All available (weekly preference)</option>
                </select>
              </div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Quiet hours</span><span className="settings-item-desc">Do not surface proactive notifications during this local-hour window.</span></div>
              <div className="settings-item-action" style={{ display: "flex", gap: 6, alignItems: "center" }}><input className="premium-input" type="number" min="0" max="23" value={form.quiet_hours_start} onChange={(e) => setForm((value) => ({ ...value, quiet_hours_start: e.target.value }))} aria-label="Quiet hours start" /><span>to</span><input className="premium-input" type="number" min="0" max="23" value={form.quiet_hours_end} onChange={(e) => setForm((value) => ({ ...value, quiet_hours_end: e.target.value }))} aria-label="Quiet hours end" /></div>
            </div>
            <div className="settings-item">
              <div className="settings-item-info"><span className="settings-item-label">Daily insight cap</span><span className="settings-item-desc">Limit proactive insight notifications to avoid noisy reminders.</span></div>
              <div className="settings-item-action"><input className="premium-input" type="number" min="0" max="20" value={form.proactive_daily_cap} onChange={(e) => setForm((value) => ({ ...value, proactive_daily_cap: e.target.value }))} aria-label="Daily insight cap" /></div>
            </div>
          </div>
          <button
            className="btn-primary settings-save-btn"
            onClick={handleSave}
            disabled={saving || (form.currency_preference === profile?.currency_preference && form.region === profile?.region && form.income_pattern === (profile?.income_pattern || "not_sure") && form.pay_cycle === (profile?.pay_cycle || "monthly") && form.risk_comfort === (profile?.risk_comfort || "not_sure") && form.household_mode === (profile?.household_mode || "individual") && form.recurring_tolerance === (profile?.recurring_tolerance || "standard") && form.cloud_ai_enabled === (profile?.cloud_ai_enabled !== false) && form.insight_frequency === (profile?.insight_frequency || "daily") && Number(form.quiet_hours_start) === (profile?.quiet_hours_start ?? 22) && Number(form.quiet_hours_end) === (profile?.quiet_hours_end ?? 7) && Number(form.proactive_daily_cap) === (profile?.proactive_daily_cap ?? 3))}
          >
            {saving ? <><Loader2 size={16} className="spin" /> Saving…</> : <><Check size={16} /> Save Preferences</>}
          </button>
        </div>

        <hr className="settings-divider" />

        <div className="settings-section">
          <h2 className="settings-title">
            <User size={18} /> Account Information
          </h2>
          <div className="settings-list">
            <div className="settings-item read-only">
              <span className="settings-item-label">Email</span>
              <span className="settings-item-value">{profile?.email || "—"}</span>
            </div>
            <div className="settings-item read-only">
              <span className="settings-item-label">User ID</span>
              <span className="settings-item-value mono">{profile?.id || "—"}</span>
            </div>
            <div className="settings-item read-only">
              <span className="settings-item-label">Member Since</span>
              <span className="settings-item-value">{formatDate(profile?.created_at)}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="settings-section">
          <h2 className="settings-title"><Wallet size={18} /> Personalize your ledger</h2>
          <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6 }}>Keep your categories and merchant names consistent without changing the original bank description.</p>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input className="premium-input" placeholder="New expense category" value={categoryName} onChange={(e) => setCategoryName(e.target.value)} />
            <button className="btn-secondary" onClick={addCategory}>Add category</button>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input className="premium-input" placeholder="Bank name / alias" value={aliasForm.alias} onChange={(e) => setAliasForm((v) => ({ ...v, alias: e.target.value }))} />
            <input className="premium-input" placeholder="Canonical merchant" value={aliasForm.canonical} onChange={(e) => setAliasForm((v) => ({ ...v, canonical: e.target.value }))} />
            <button className="btn-secondary" onClick={addAlias}>Save alias</button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {customCategories.map((item) => <span key={item.id} className="category-pill active">{item.name}</span>)}
            {merchantAliases.map((item) => <button key={item.id} className="category-pill" onClick={() => removeAlias(item.id)} title="Remove alias">{item.alias_key} → {item.canonical} ×</button>)}
          </div>
        </div>
      </div>

      {/* ── Privacy & Data ───────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="settings-section">
          <h2 className="settings-title"><Shield size={18} /> Privacy & your data</h2>
          <p style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6, margin: "0 0 16px" }}>
            Export a portable copy of your profile, accounts, transactions, goals, investments, conversations, and category corrections. Uploaded statement files and webhook secrets are never included.
          </p>
          <button className="btn-secondary" onClick={handleFullExport} disabled={exportingData}>
            <Download size={15} /> {exportingData ? "Preparing export…" : "Download all my data"}
          </button>
        </div>
      </div>

      {/* ── Danger Zone ──────────────────────────────────────────────── */}
      <div className="card profile-danger-card">
        <div className="danger-content">
          <div className="danger-icon-wrap">
            <LogOut size={20} className="danger-icon" />
          </div>
          <div className="danger-text">
            <h2 className="danger-title">Sign Out</h2>
            <p className="danger-desc">You'll be signed out of your account on this device.</p>
          </div>
        </div>
        
        <div className="danger-actions">
          {!confirmSignOut ? (
            <button className="btn-danger-premium" onClick={() => setConfirmSignOut(true)}>
              Sign Out
            </button>
          ) : (
            <div className="danger-confirm-row fade-in">
              <span className="danger-confirm-text">Are you sure?</span>
              <button className="btn-danger-premium" onClick={onSignOut}>
                Yes, sign out
              </button>
              <button className="btn-secondary" onClick={() => setConfirmSignOut(false)}>
                Cancel
              </button>
            </div>
          )}
        </div>

        <div style={{ borderTop: "1px solid var(--border)", marginTop: 20, paddingTop: 20 }}>
          <div className="danger-content">
            <div className="danger-icon-wrap"><Trash2 size={20} className="danger-icon" /></div>
            <div className="danger-text">
              <h2 className="danger-title">Delete all Ledger data</h2>
              <p className="danger-desc">This permanently removes your financial history, accounts, goals, investments, AI conversations, and profile. Download an export first if you may need it later.</p>
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 14 }}>
            <input aria-label="Type DELETE to confirm" placeholder="Type DELETE to confirm" value={deleteConfirmation}
              onChange={e => setDeleteConfirmation(e.target.value)} style={{ maxWidth: 220 }} />
            <button className="btn-danger-premium" onClick={handleDeleteData} disabled={deleteConfirmation !== "DELETE" || deletingData}>
              {deletingData ? "Deleting…" : "Permanently delete data"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
