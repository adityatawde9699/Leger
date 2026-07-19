import React from "react";
import { apiFetch } from "../lib";
import { AlertCircle, Lightbulb, CheckCircle, Info, Zap, X, ChevronRight } from "lucide-react";

const TYPE_CONFIG = {
  warning:  { icon: <AlertCircle  size={14} />, color: "var(--negative)", bg: "var(--negative-soft)", border: "rgba(255,45,45,0.4)", label: "Warning"  },
  tip:      { icon: <Lightbulb    size={14} />, color: "var(--warning)", bg: "rgba(250,204,21,0.12)", border: "rgba(250,204,21,0.4)", label: "Tip"      },
  positive: { icon: <CheckCircle  size={14} />, color: "var(--positive)", bg: "var(--positive-soft)", border: "rgba(168,255,47,0.3)", label: "Great"    },
  info:     { icon: <Info         size={14} />, color: "var(--info)", bg: "rgba(56,189,248,0.12)", border: "rgba(56,189,248,0.3)", label: "Info"     },
};

const PRIORITY_LABEL = { 5: "Critical", 4: "Important", 3: "Notable", 2: "Informational", 1: "Minor" };

export default function ProactiveInsights({ onNavigate }) {
  const [insights,   setInsights]   = React.useState([]);
  const [loading,    setLoading]    = React.useState(true);
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
    apiFetch("/summary/proactive")
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

  const visible = insights.filter((ins, i) => !dismissed[`${ins.text}_${i}`]);

  if (loading) {
    return (
      <div className="proactive-card card">
        <div className="proactive-title" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <Zap size={16} style={{ color: "var(--info)" }} />
          <span>AI Insights</span>
          <div className="skeleton" style={{ width: 40, height: 20, borderRadius: 10, marginLeft: "auto" }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 52, borderRadius: 12 }} />
          ))}
        </div>
      </div>
    );
  }

  if (!visible.length) return null;

  return (
    <div className="proactive-card card">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <Zap size={16} style={{ color: "var(--info)" }} />
        <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>AI Insights</span>
        <span style={{
          marginLeft: "auto", fontSize: 11, padding: "2px 10px", borderRadius: 20,
          background: "var(--surface-secondary)", color: "var(--text-muted)", fontWeight: 600,
        }}>
          {visible.length} insights
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {visible.map((ins, i) => {
          const cfg = TYPE_CONFIG[ins.type] || TYPE_CONFIG.info;
          const key = `${ins.text}_${i}`;
          return (
            <div key={key}
              style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "12px 14px",
                background: cfg.bg,
                border: `1px solid ${cfg.border}`,
                borderLeft: `4px solid ${cfg.color}`,
                borderRadius: 12,
                position: "relative",
                transition: "transform 0.15s, box-shadow 0.15s",
              }}
              onMouseEnter={e => e.currentTarget.style.transform = "translateY(-1px)"}
              onMouseLeave={e => e.currentTarget.style.transform = ""}
            >
              {/* Priority badge */}
              {ins.priority >= 4 && (
                <div style={{
                  position: "absolute", top: -6, right: 36, fontSize: 9, fontWeight: 800,
                  padding: "1px 6px", borderRadius: 6, textTransform: "uppercase",
                  background: ins.priority === 5 ? "var(--negative)" : "var(--warning)", color: "#fff",
                }}>
                  {PRIORITY_LABEL[ins.priority]}
                </div>
              )}

              <div style={{ color: cfg.color, marginTop: 1, flexShrink: 0 }}>
                {cfg.icon}
              </div>

              <div style={{ flex: 1 }}>
                <p style={{ fontSize: 13, lineHeight: 1.55, margin: 0, color: "var(--text-primary)", fontWeight: 500 }}>
                  {ins.text}
                </p>
                {ins.category && (
                  <button
                    onClick={() => onNavigate?.(`/transactions?category=${ins.category}`)}
                    style={{
                      marginTop: 6, fontSize: 11, color: cfg.color, background: "none",
                      border: "none", padding: 0, cursor: "pointer", display: "flex",
                      alignItems: "center", gap: 3, fontWeight: 600,
                    }}
                  >
                    View {ins.category} <ChevronRight size={10} />
                  </button>
                )}
              </div>

              {/* Type label */}
              <span style={{
                fontSize: 10, padding: "2px 7px", borderRadius: 8, fontWeight: 700,
                color: cfg.color, background: "transparent",
                border: `1px solid ${cfg.border}`, textTransform: "uppercase",
                flexShrink: 0, alignSelf: "flex-start",
              }}>
                {cfg.label}
              </span>

              {/* Dismiss button */}
              <button onClick={() => dismiss(key)}
                style={{
                  background: "none", border: "none", color: "var(--text-muted)",
                  cursor: "pointer", padding: "0 2px", flexShrink: 0, fontSize: 14,
                  lineHeight: 1, marginTop: -2,
                }}>
                <X size={13} />
              </button>
            </div>
          );
        })}
      </div>

      {insights.length > visible.length && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)", textAlign: "center" }}>
          {insights.length - visible.length} insight(s) dismissed · Resets in 7 days
        </div>
      )}
    </div>
  );
}
