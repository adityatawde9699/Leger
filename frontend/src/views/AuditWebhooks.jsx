import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, KEYS } from "../lib";
import { useToast } from "../components/ui";
import {
  Shield, Clock, Edit3, Trash2, Plus, Globe, AlertCircle,
} from "lucide-react";

function timeAgo(dateStr) {
  const d = new Date(dateStr);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const ACTION_ICONS = {
  create: <Plus size={14} />,
  update: <Edit3 size={14} />,
  delete: <Trash2 size={14} />,
};

const ACTION_COLORS = {
  create: "var(--positive)",
  update: "var(--primary)",
  delete: "var(--negative)",
};

export default function AuditWebhooks() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [tab, setTab] = React.useState("audit");
  const [showForm, setShowForm] = React.useState(false);
  const [form, setForm] = React.useState({ url: "", events: "transaction.created,transaction.deleted", secret: "" });
  const [saving, setSaving] = React.useState(false);

  const auditQuery = useQuery({ queryKey: KEYS.audit(), queryFn: () => apiFetch("/audit?limit=100") });
  const hooksQuery = useQuery({ queryKey: KEYS.webhooks(), queryFn: () => apiFetch("/webhooks") });
  const logs = auditQuery.data || [];
  const hooks = hooksQuery.data || [];
  const loading = auditQuery.isLoading || hooksQuery.isLoading;

  async function createHook(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/webhooks", { method: "POST", body: JSON.stringify(form) });
      setForm({ url: "", events: "transaction.created,transaction.deleted", secret: "" });
      setShowForm(false);
      queryClient.invalidateQueries({ queryKey: KEYS.webhooks() });
      toast("Webhook registered", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally { setSaving(false); }
  }

  async function deleteHook(id) {
    try {
      await apiFetch(`/webhooks/${id}`, { method: "DELETE" });
      queryClient.invalidateQueries({ queryKey: KEYS.webhooks() });
      toast("Webhook removed", "success");
    } catch (e) { toast(e.message, "error"); }
  }

  return (
    <div className="view-audit">
      <div className="page-title-block">
        <h1 className="page-title">Audit & Webhooks</h1>
        <p className="page-subtitle">Activity log and event integrations</p>
      </div>

      {/* Tab toggle */}
      <div className="type-toggle" style={{ marginBottom: 20 }}>
        <button className={`type-btn${tab === "audit" ? " active expense" : ""}`} onClick={() => setTab("audit")} style={tab === "audit" ? { borderColor: "var(--primary)", background: "rgba(56,189,248,0.12)", color: "var(--primary)" } : {}}>
          <Shield size={14} style={{ marginRight: 4 }} /> Audit Log
        </button>
        <button className={`type-btn${tab === "webhooks" ? " active income" : ""}`} onClick={() => setTab("webhooks")}>
          <Globe size={14} style={{ marginRight: 4 }} /> Webhooks
        </button>
      </div>

      {/* Audit Log */}
      {tab === "audit" && (
        <div className="card">
          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[1,2,3,4,5].map(i => <div key={i} className="skeleton" style={{ height: 44, borderRadius: 8 }} />)}
            </div>
          ) : logs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📋</div>
              <div className="empty-state-title">No activity yet</div>
              <div className="empty-state-sub">Actions will appear here as you use the app</div>
            </div>
          ) : (
            <div className="audit-list">
              {logs.map(log => (
                <div className="audit-item" key={log.id}>
                  <div className="audit-icon" style={{ color: ACTION_COLORS[log.action] || "var(--text-muted)" }}>
                    {ACTION_ICONS[log.action] || <Edit3 size={14} />}
                  </div>
                  <div className="audit-content">
                    <div className="audit-action">
                      <span className="audit-action-badge" style={{ color: ACTION_COLORS[log.action] }}>{log.action}</span>
                      <span className="audit-resource">{log.resource_type}</span>
                      {log.resource_id && <span className="audit-resource-id">{log.resource_id.slice(0, 8)}…</span>}
                    </div>
                    {log.details && (
                      <div className="audit-details">{log.details.length > 120 ? log.details.slice(0, 120) + "…" : log.details}</div>
                    )}
                  </div>
                  <div className="audit-meta">
                    <Clock size={12} /> {timeAgo(log.created_at)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Webhooks */}
      {tab === "webhooks" && (
        <div>
          {/* Existing webhooks */}
          {hooks.length > 0 && (
            <div className="webhook-grid" style={{ marginBottom: 16 }}>
              {hooks.map(hook => (
                <div className={`card webhook-card${!hook.is_active ? " disabled" : ""}`} key={hook.id}>
                  <div className="webhook-card-top">
                    <div>
                      <div className="webhook-url">{hook.url.length > 50 ? hook.url.slice(0, 50) + "…" : hook.url}</div>
                      <div className="webhook-events">
                        {hook.events.split(",").map(e => (
                          <span className="webhook-event-badge" key={e}>{e.trim()}</span>
                        ))}
                      </div>
                    </div>
                    <button className="tx-delete-btn" onClick={() => deleteHook(hook.id)} aria-label="Delete webhook">
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <div className="webhook-meta">
                    <span className={`webhook-status ${hook.is_active ? "active" : "inactive"}`}>
                      {hook.is_active ? "Active" : "Disabled"}
                    </span>
                    {hook.failure_count > 0 && (
                      <span className="webhook-failures">
                        <AlertCircle size={12} /> {hook.failure_count} failures
                      </span>
                    )}
                    {hook.last_triggered && <span>Last: {timeAgo(hook.last_triggered)}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Add webhook */}
          {!showForm ? (
            <button className="btn-primary" onClick={() => setShowForm(true)} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Plus size={14} /> Register Webhook
            </button>
          ) : (
            <div className="card">
              <div className="form-section-title">New Webhook</div>
              <form onSubmit={createHook}>
                <div className="form-field">
                  <label className="form-label">Endpoint URL</label>
                  <input required placeholder="https://your-server.com/webhook" value={form.url}
                    onChange={e => setForm({ ...form, url: e.target.value })} />
                </div>
                <div className="form-grid-2">
                  <div className="form-field">
                    <label className="form-label">Events (comma-separated)</label>
                    <input required placeholder="transaction.created,budget.exceeded" value={form.events}
                      onChange={e => setForm({ ...form, events: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">HMAC Secret (min 16 chars)</label>
                    <input required type="password" placeholder="your-secret-key-here" value={form.secret}
                      onChange={e => setForm({ ...form, secret: e.target.value })} minLength={16} />
                  </div>
                </div>
                <div className="form-actions">
                  <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Registering…" : "Register"}</button>
                  <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
