import React from "react";
import { apiFetch, formatRange } from "../lib";
import { X, ChevronRight } from "lucide-react";

const TYPE_CONFIG = {
  warning:  { dot: "var(--negative)", label: "Warning" },
  tip:      { dot: "var(--warning)",  label: "Tip" },
  positive: { dot: "var(--positive)", label: "Going well" },
  info:     { dot: "var(--text-muted)", label: "Note" },
};

const PRIORITY_LABEL = { 5: "Critical", 4: "Important", 3: "Notable", 2: "Informational", 1: "Minor" };

export default function ProactiveInsights({ onNavigate }) {
  const [insights,   setInsights]   = React.useState([]);
  const [loading,    setLoading]    = React.useState(true);
  const [feedback,   setFeedback]   = React.useState({});
  const [openWhy,    setOpenWhy]    = React.useState(null);
  const [dismissed,  setDismissed]  = React.useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem("dismissed_insights") || "{}");
      const now    = Date.now();
      // Clean up expired dismissals (7 days)
      const valid = Object.fromEntries(
        Object.entries(stored).filter(([, ts]) => now - ts < 7 * 24 * 3600 * 1000)
      );
      return valid;
    } catch { return {}; }
  });

  React.useEffect(() => {
    apiFetch("/insights/proactive")
      .then((data) => {
        // Sort by priority descending
        const sorted = [...(data || [])].sort((a, b) => (b.priority || 0) - (a.priority || 0));
        setInsights(sorted);
      })
      .catch(() => setInsights([]))
      .finally(() => setLoading(false));
  }, []);

  const dismiss = (key) => {
    const next = { ...dismissed, [key]: Date.now() };
    setDismissed(next);
    localStorage.setItem("dismissed_insights", JSON.stringify(next));
  };

  const sendFeedback = async (insight, value) => {
    if (!insight.id || feedback[insight.id]) return;
    setFeedback((current) => ({ ...current, [insight.id]: value }));
    try {
      await apiFetch("/insights/feedback", {
        method: "POST",
        body: JSON.stringify({ insight_id: insight.id, feedback: value }),
      });
    } catch {
      // Feedback should never block or make the financial workflow noisy.
    }
  };

  const visible = insights.filter((ins, i) => !dismissed[`${ins.text}_${i}`]);

  if (loading) {
    return (
      <div className="card" style={{ marginTop: 16 }}>
        <div className="chart-card-header" style={{ marginBottom: 12 }}><div className="chart-title">Advisor notes</div></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 44, borderRadius: 8 }} />
          ))}
        </div>
      </div>
    );
  }

  if (!visible.length) return null;

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="chart-card-header" style={{ marginBottom: 8 }}>
        <div>
          <div className="chart-title">Advisor notes <span className="num" style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 4 }}>{visible.length}</span></div>
          <div className="chart-subtitle">Generated from your transactions, ordered by priority</div>
        </div>
      </div>

      <div className="ledger-list">
        {visible.map((ins, i) => {
          const cfg = TYPE_CONFIG[ins.type] || TYPE_CONFIG.info;
          const key = `${ins.text}_${i}`;
          const hasWhy = ins.evidence?.length > 0 || ins.data_quality?.coverage;
          return (
            <div key={key} className="ledger-row" style={{ gridTemplateColumns: "auto 1fr auto", alignItems: "start", padding: "12px 0" }}>
              <span className="status-dot" style={{ background: cfg.dot, marginTop: 8 }} aria-hidden="true" />
              <div style={{ minWidth: 0 }}>
                <p style={{ fontSize: 14, lineHeight: "22px", margin: 0, color: "var(--text-primary)" }}>
                  {ins.text}
                </p>
                <div className="sub" style={{ marginTop: 4 }}>
                  {cfg.label}{ins.priority >= 4 ? ` · ${PRIORITY_LABEL[ins.priority]} priority` : ""}
                  {ins.action && <> · Next step: {ins.action}</>}
                </div>
                <div className="insight-actions">
                  {ins.category && (
                    <button className="btn-link" onClick={() => onNavigate?.("transactions")} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, padding: 0, color: "var(--text-primary)" }}>
                      View {ins.category} <ChevronRight size={12} />
                    </button>
                  )}
                  {hasWhy && (
                    <button className="btn-link" aria-expanded={openWhy === key} onClick={() => setOpenWhy(openWhy === key ? null : key)} style={{ fontSize: 12, padding: 0 }}>
                      {openWhy === key ? "Hide why" : "Why this?"}
                    </button>
                  )}
                  {ins.id && (feedback[ins.id] ? (
                    <span>Marked {feedback[ins.id].replace("_", " ")}</span>
                  ) : (
                    <span className="insight-feedback">
                      <span>Useful?</span>
                      {[["helpful", "Yes"], ["inaccurate", "Needs correction"], ["too_generic", "Too generic"]].map(([value, label]) => (
                        <button key={value} className="btn-link" onClick={() => sendFeedback(ins, value)} style={{ fontSize: 12, padding: 0 }}>
                          {label}
                        </button>
                      ))}
                    </span>
                  ))}
                </div>
                {hasWhy && openWhy === key && (
                  <div className="insight-why">
                    {ins.evidence?.length > 0 && (
                      <div>Based on {ins.evidence.length} transaction{ins.evidence.length === 1 ? "" : "s"}
                        {ins.category ? ` in ${ins.category}` : ""}.</div>
                    )}
                    {ins.data_quality?.period_start && (
                      <div>Data: {formatRange(ins.data_quality.period_start, ins.data_quality.period_end) || `${ins.data_quality.period_start} – ${ins.data_quality.period_end}`} · {ins.data_quality.coverage} coverage.</div>
                    )}
                    <div>Confidence: {ins.confidence || "medium"} · {ins.source === "ai" ? "AI explanation" : "Ledger calculation"}.</div>
                  </div>
                )}
              </div>

              {/* Seven-day snooze: the insight can return after the user has had time to act. */}
              <button className="toast-close" aria-label="Snooze insight for 7 days" title="Snooze for 7 days" onClick={() => { dismiss(key); sendFeedback(ins, "snoozed"); }}>
                <X size={14} strokeWidth={1.5} />
              </button>
            </div>
          );
        })}
      </div>

      {insights.length > visible.length && (
        <div style={{ marginTop: 12, fontSize: 12, color: "var(--text-muted)" }}>
          {insights.length - visible.length} snoozed for 7 days
        </div>
      )}
    </div>
  );
}
