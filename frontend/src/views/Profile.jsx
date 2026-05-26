import React, { useState, useEffect, useCallback } from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import {
  User, Mail, Calendar, TrendingUp, TrendingDown,
  DollarSign, CreditCard, Target, Edit3, Check, X,
  LogOut, AlertTriangle, Shield, Wallet, BarChart3,
  Loader2, RefreshCw,
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
  const [profile, setProfile] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const [form, setForm] = useState({ display_name: "", currency_preference: "INR" });

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
          {[1,2,3,4].map(i => (
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
    <div className="view-profile">
      {/* ── Profile Hero ─────────────────────────────────────────────── */}
      <div className="profile-hero card">
        <div className="profile-avatar-wrap">
          <div
            className="profile-avatar-lg"
            style={{ background: gradient }}
            aria-label={`Avatar for ${displayName}`}
          >
            {initials}
          </div>
          <div className="profile-avatar-badge">
            <Shield size={12} />
          </div>
        </div>

        <div className="profile-hero-info">
          {editing ? (
            <div className="profile-edit-inline">
              <input
                autoFocus
                className="profile-name-input"
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
            <div className="profile-name-row">
              <h1 className="profile-name">{displayName}</h1>
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
          className="profile-refresh-btn"
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
          <div key={label} className="card profile-stat-card">
            <div className="profile-stat-icon" style={{ background: bg, color }}>
              <Icon size={16} />
            </div>
            <div className="profile-stat-value" style={{ color }}>
              {isCount ? value.toLocaleString("en-IN") : value}
            </div>
            <div className="profile-stat-label">{label}</div>
          </div>
        ))}
      </div>

      {/* ── Preferences Section ──────────────────────────────────────── */}
      <div className="card profile-section">
        <h2 className="profile-section-title">
          <CreditCard size={18} /> Preferences
        </h2>
        <div className="form-grid-2" style={{ marginBottom: 0 }}>
          <div className="form-field" style={{ marginBottom: 0 }}>
            <label className="form-label">Currency</label>
            <select
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
          <div className="form-field" style={{ marginBottom: 0 }}>
            <label className="form-label">Display Name</label>
            <input
              value={form.display_name}
              onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
              placeholder="How should we address you?"
              maxLength={128}
            />
          </div>
        </div>
        <button
          className="btn-primary"
          style={{ marginTop: 20 }}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? <><Loader2 size={16} className="spin" /> Saving…</> : <><Check size={16} /> Save Preferences</>}
        </button>
      </div>

      {/* ── Account Info ─────────────────────────────────────────────── */}
      <div className="card profile-section">
        <h2 className="profile-section-title">
          <User size={18} /> Account Information
        </h2>
        <div className="profile-info-rows">
          <div className="profile-info-row">
            <span className="profile-info-label">Email</span>
            <span className="profile-info-value">{profile?.email || "—"}</span>
          </div>
          <div className="profile-info-row">
            <span className="profile-info-label">User ID</span>
            <span className="profile-info-value profile-id">{profile?.id || "—"}</span>
          </div>
          <div className="profile-info-row">
            <span className="profile-info-label">Member Since</span>
            <span className="profile-info-value">{formatDate(profile?.created_at)}</span>
          </div>
          <div className="profile-info-row">
            <span className="profile-info-label">Currency</span>
            <span className="profile-info-value">{profile?.currency_preference || "INR"}</span>
          </div>
        </div>
      </div>

      {/* ── Danger Zone ──────────────────────────────────────────────── */}
      <div className="card profile-section danger-zone">
        <h2 className="profile-section-title danger-title">
          <AlertTriangle size={18} /> Sign Out
        </h2>
        <p className="danger-desc">
          You'll be signed out of your account on this device.
        </p>
        {!confirmSignOut ? (
          <button
            className="btn-danger"
            onClick={() => setConfirmSignOut(true)}
          >
            <LogOut size={16} /> Sign Out
          </button>
        ) : (
          <div className="danger-confirm-row">
            <span className="danger-confirm-text">Are you sure?</span>
            <button className="btn-danger" onClick={onSignOut}>
              Yes, sign out
            </button>
            <button className="btn-secondary" onClick={() => setConfirmSignOut(false)}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
