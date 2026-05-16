import React from "react";
import { apiFetch, money } from "../lib";
import { AlertCircle, TrendingUp, Lightbulb, CheckCircle, Info } from "lucide-react";

const ICONS = {
  warning: <AlertCircle size={15} />,
  tip: <Lightbulb size={15} />,
  positive: <CheckCircle size={15} />,
  info: <Info size={15} />,
};

export default function ProactiveInsights() {
  const [insights, setInsights] = React.useState([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    apiFetch("/insights/proactive")
      .then(setInsights)
      .catch(() => setInsights([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="proactive-card card">
        <div className="proactive-title">AI Insights</div>
        <div className="proactive-loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 42, borderRadius: 8 }} />
          ))}
        </div>
      </div>
    );
  }

  if (!insights.length) return null;

  return (
    <div className="proactive-card card">
      <div className="proactive-title">
        <Lightbulb size={16} className="icon-accent" /> AI Insights
      </div>
      <div className="proactive-list">
        {insights.map((insight, i) => (
          <div key={i} className={`proactive-item proactive-${insight.type}`}>
            <div className="proactive-icon">{ICONS[insight.type] || ICONS.info}</div>
            <p>{insight.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
