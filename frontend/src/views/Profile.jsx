import React, { useState, useEffect, useCallback, useRef } from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import {
  User, Mail, Calendar, TrendingUp, TrendingDown,
  DollarSign, CreditCard, Target, Edit3, Check, X,
  LogOut, AlertTriangle, Shield, Wallet, BarChart3,
  Loader2, RefreshCw, Camera
} from "lucide-react";

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
  const [form, setForm] = useState({ display_name: "", currency_preference: "INR" });
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    try {
      const [p, s] = await Promise.all([
        apiFetch("/profile"),
        apiFetch("/profile/stats"),
      ]);
      setProfile(p);
      setStats(s);
      setForm({ display_name: p.display_name || "", currency_preference: p.currency_preference || "INR" });
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadProfile(); }, [loadProfile]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await apiFetch("/profile", {
        method: "PUT",
        body: JSON.stringify({
          display_name: form.display_name.trim() || null,
          currency_preference: form.currency_preference,
        }),
      });
      setProfile(updated);
      setEditing(false);
      toast("Profile updated", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setForm({ display_name: profile?.display_name || "", currency_preference: profile?.currency_preference || "INR" });
    setEditing(false);
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
      isCount: true, color: "#6366f1", bg: "#ede9fe",
    },
    {
      icon: TrendingUp, label: "Total Income", value: money(stats?.total_income || 0),
      color: "#10b981", bg: "#d1fae5",
    },
    {
      icon: TrendingDown, label: "Total Expenses", value: money(stats?.total_expenses || 0),
      color: "#f43f5e", bg: "#ffe4e6",
    },
    {
      icon: DollarSign, label: "Net Balance", value: money(stats?.net_balance || 0),
      color: Number(stats?.net_balance || 0) >= 0 ? "#10b981" : "#f43f5e",
      bg: Number(stats?.net_balance || 0) >= 0 ? "#d1fae5" : "#ffe4e6",
    },
    {
      icon: Wallet, label: "Accounts", value: stats?.accounts_count ?? "—",
      isCount: true, color: "#0ea5e9", bg: "#e0f2fe",
    },
    {
      icon: Target, label: "Budgets", value: stats?.budgets_count ?? "—",
      isCount: true, color: "#f59e0b", bg: "#fef3c7",
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
          <div key={label} className="card profile-stat-card glass-card">
            <div className="profile-stat-icon premium-icon" style={{ background: bg, color }}>
              <Icon size={16} />
            </div>
            <div className="profile-stat-value" style={{ color }}>
              {isCount ? value.toLocaleString("en-IN") : value}
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
                <span className="settings-item-desc">Choose your primary display currency</span>
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
                </select>
              </div>
            </div>
          </div>
          <button
            className="btn-primary settings-save-btn"
            onClick={handleSave}
            disabled={saving || (form.currency_preference === profile?.currency_preference)}
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
      </div>
    </div>
  );
}
