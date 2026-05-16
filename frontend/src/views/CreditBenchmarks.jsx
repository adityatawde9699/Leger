import React from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import {
  TrendingUp, TrendingDown, BarChart3, Users, ArrowUp, ArrowDown,
  Gauge, Heart, Shield, Zap, Lightbulb, DollarSign,
} from "lucide-react";

/* ─── Credit Health Gauge ──────────────────────── */
function CreditGauge({ score, grade, color }) {
  const pct = Math.min(100, Math.max(0, ((score - 300) / 600) * 100));
  return (
    <div className="credit-gauge">
      <div className="gauge-ring">
        <svg viewBox="0 0 120 120" width="180" height="180">
          <circle cx="60" cy="60" r="52" fill="none" stroke="#f1f5f9" strokeWidth="10" strokeDasharray="245" strokeDashoffset="0" transform="rotate(-90 60 60)" />
          <circle cx="60" cy="60" r="52" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray="245" strokeDashoffset={245 - (245 * pct) / 100} transform="rotate(-90 60 60)" style={{ transition: "stroke-dashoffset 1s ease" }} />
        </svg>
        <div className="gauge-center">
          <div className="gauge-score" style={{ color }}>{score}</div>
          <div className="gauge-grade">{grade}</div>
        </div>
      </div>
      <div className="gauge-range">
        <span>300</span>
        <span>900</span>
      </div>
    </div>
  );
}

export default function CreditBenchmarks() {
  const toast = useToast();
  const [tab, setTab] = React.useState("credit");
  const [credit, setCredit] = React.useState(null);
  const [benchmarks, setBenchmarks] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    Promise.all([
      apiFetch("/credit-health").then(setCredit).catch(() => {}),
      apiFetch("/benchmarks").then(setBenchmarks).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const FACTOR_ICONS = { savings: Heart, budget_adherence: Shield, consistency: Zap, diversity: BarChart3, credit_utilization: DollarSign };

  return (
    <div className="view-credit">
      <div className="page-title-block">
        <h1 className="page-title">Financial Health</h1>
        <p className="page-subtitle">Credit score, spending benchmarks & insights</p>
      </div>

      <div className="type-toggle" style={{ marginBottom: 20 }}>
        <button className={`type-btn${tab === "credit" ? " active expense" : ""}`} onClick={() => setTab("credit")} style={tab === "credit" ? { borderColor: "var(--accent)", background: "#eff6ff", color: "var(--accent)" } : {}}>
          <Gauge size={14} style={{ marginRight: 4 }} /> Credit Score
        </button>
        <button className={`type-btn${tab === "benchmarks" ? " active income" : ""}`} onClick={() => setTab("benchmarks")}>
          <Users size={14} style={{ marginRight: 4 }} /> Benchmarks
        </button>
      </div>

      {/* Credit Health */}
      {tab === "credit" && (
        <div>
          {loading || !credit ? (
            <div className="card"><div className="skeleton" style={{ height: 200, borderRadius: 12 }} /></div>
          ) : (
            <>
              <div className="card credit-main-card">
                <CreditGauge score={credit.score} grade={credit.grade} color={credit.color} />
              </div>

              <div className="account-grid" style={{ marginTop: 20 }}>
                {Object.entries(credit.breakdown).map(([key, factor]) => {
                  const Icon = FACTOR_ICONS[key] || Zap;
                  const pct = Math.round((factor.score / factor.max) * 100);
                  return (
                    <div className="card credit-factor-card" key={key}>
                      <div className="credit-factor-top">
                        <Icon size={16} className="icon-accent" />
                        <span className="credit-factor-name">{key.replace(/_/g, " ")}</span>
                      </div>
                      <div className="credit-factor-bar-wrap">
                        <div className="credit-factor-bar" style={{ width: `${pct}%`, background: pct > 70 ? "#16a34a" : pct > 40 ? "#f59e0b" : "#dc2626" }} />
                      </div>
                      <div className="credit-factor-score">{factor.score}/{factor.max}</div>
                    </div>
                  );
                })}
              </div>

              {credit.tips.length > 0 && (
                <div className="card" style={{ marginTop: 20 }}>
                  <div className="form-section-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Lightbulb size={16} /> Tips to Improve
                  </div>
                  <div className="insights-list">
                    {credit.tips.map((tip, i) => (
                      <div className="insight-item" key={i}>
                        <ArrowUp size={14} className="icon-positive" />
                        <p>{tip}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Community Benchmarks */}
      {tab === "benchmarks" && (
        <div>
          {loading || !benchmarks ? (
            <div className="card"><div className="skeleton" style={{ height: 200, borderRadius: 12 }} /></div>
          ) : (
            <>
              <div className="card hero-card" style={{ marginBottom: 20 }}>
                <div className="hero-label"><Users size={15} /> Your Spending Rank</div>
                <div className="hero-amount">{benchmarks.overall_percentile}th percentile</div>
                <div className="hero-change muted">
                  You spend {benchmarks.overall_percentile > 50 ? "more" : "less"} than {benchmarks.overall_percentile}% of users • Median: {money(benchmarks.benchmark_median)}
                </div>
              </div>

              <div className="card">
                <div className="form-section-title">Category Comparison</div>
                <div className="benchmark-list">
                  {benchmarks.categories.map(cat => (
                    <div className="benchmark-row" key={cat.category}>
                      <div className="benchmark-row-left">
                        <span className="benchmark-cat">{cat.category}</span>
                        <span className="benchmark-spend">{money(cat.your_spend)}</span>
                      </div>
                      <div className="benchmark-bar-wrap">
                        <div className={`benchmark-bar benchmark-${cat.status}`} style={{ width: `${Math.min(100, cat.percentile)}%` }} />
                        <div className="benchmark-median-mark" style={{ left: "50%" }} />
                      </div>
                      <div className="benchmark-row-right">
                        <span className={`benchmark-badge benchmark-${cat.status}`}>{cat.label}</span>
                        <span className="benchmark-pct">P{cat.percentile}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="benchmark-footer">
                  Based on {benchmarks.sample_size} urban users • {benchmarks.methodology}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
