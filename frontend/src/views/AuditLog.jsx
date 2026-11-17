import React from "react";
import { apiFetch } from "../lib";
import { useToast } from "../components/ui";
import { Clock, Edit3, Trash2, Plus, ClipboardList } from "lucide-react";

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

export default function AuditLog() {
  const toast = useToast();
  const [logs, setLogs] = React.useState([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    apiFetch("/audit?limit=100")
      .then(setLogs)
      .catch((e) => toast(e.message, "error"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="view-audit">
      <div className="page-title-block">
        <h1 className="page-title">Audit log</h1>
        <p className="page-subtitle">Every change to your ledger</p>
      </div>

      <div className="card">
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1,2,3,4,5].map(i => <div key={i} className="skeleton" style={{ height: 44, borderRadius: 8 }} />)}
          </div>
        ) : logs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon"><ClipboardList size={18} strokeWidth={1.5} /></div>
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
    </div>
  );
}
