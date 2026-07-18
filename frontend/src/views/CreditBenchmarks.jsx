import React from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, money, KEYS } from "../lib";
import {
  BarChart3, Users, ArrowUp, Gauge, Heart, Shield, Zap, Lightbulb, DollarSign, TrendingUp,
} from "lucide-react";

function CreditGauge({ score, grade, color }) {
  const pct = Math.min(100, Math.max(0, ((score - 300) / 600) * 100));
  const circumference = 2 * Math.PI * 52;
  const offset = circumference - (circumference * pct) / 100;

  return (
    <div className="credit-gauge">
      <div className="gauge-ring" style={{ position: 'relative', display: 'inline-block' }}>
        <svg viewBox="0 0 120 120" width="200" height="200">
          {/* Background ring */}
          <circle cx="60" cy="60" r="52" fill="none" stroke="var(--border)" strokeWidth="12"
            strokeDasharray={circumference} strokeDashoffset="0" transform="rotate(-90 60 60)" />
          {/* Score ring */}
          <circle cx="60" cy="60" r="52" fill="none" stroke={color} strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform="rotate(-90 60 60)"
            style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)', filter: `drop-shadow(0 0 8px ${color}40)` }} />
        </svg>
        <div style={{
          position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          textAlign: 'center',
        }}>
          <div className="gauge-score" style={{ color }}>{score}</div>
          <div className="gauge-grade">{grade}</div>
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', width: 200, marginTop: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>300</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>900</span>
      </div>
    </div>
  );
}

export default function CreditBenchmarks() {
  const [tab, setTab] = React.useState("credit");
  const { data: credit, isLoading: creditLoading } = useQuery({
    queryKey: KEYS.creditHealth(),
    queryFn: () => apiFetch("/credit-health"),
  });
  const { data: benchmarks, isLoading: benchmarksLoading } = useQuery({
    queryKey: KEYS.benchmarks(),
    queryFn: () => apiFetch("/benchmarks"),
  });
  const loading = creditLoading || benchmarksLoading;

  const FACTOR_ICONS = {
    savings:           Heart,
    budget_adherence:  Shield,
    consistency:       Zap,
    diversity:         BarChart3,
    credit_utilization: DollarSign,
  };

  const TABS = [
    { id: "credit",     label: "Credit Score",  Icon: Gauge },
    { id: "benchmarks", label: "Benchmarks",    Icon: Users },
  ];

  return (
    <div className="view-credit">
      <div style={{ marginBottom: 32 }}>
        <h1 className="page-title">Financial Health</h1>
        <p className="page-subtitle" style={{ marginBottom: 0 }}>Credit score, spending benchmarks & insights</p>
      </div>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 28, background: 'var(--bg)', padding: 4, borderRadius: 12, width: 'fit-content' }}>
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 20px', borderRadius: 10, border: 'none', cursor: 'pointer',
              fontSize: 14, fontWeight: 600, transition: 'all 0.2s',
              background: tab === id ? 'var(--surface)' : 'transparent',
              color: tab === id ? 'var(--primary)' : 'var(--text-secondary)',
              boxShadow: tab === id ? 'var(--shadow)' : 'none',
            }}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {/* Credit tab */}
      {tab === "credit" && (
        <div>
          {loading || !credit ? (
            <div className="card">
              <div className="skeleton" style={{ height: 220, borderRadius: 12 }} />
            </div>
          ) : (
            <>
              <div className="card credit-main-card" style={{ marginBottom: 24 }}>
                <CreditGauge score={credit.score} grade={credit.grade} color={credit.color} />
              </div>

              <div className="account-grid" style={{ marginBottom: 24 }}>
                {Object.entries(credit.breakdown).map(([key, factor]) => {
                  const Icon = FACTOR_ICONS[key] || Zap;
                  const pct  = Math.round((factor.score / factor.max) * 100);
                  const barColor = pct > 70 ? 'var(--positive)' : pct > 40 ? 'var(--warning)' : 'var(--negative)';
                  return (
                    <div className="card credit-factor-card" key={key}>
                      <div className="credit-factor-top">
                        <div style={{ width: 36, height: 36, borderRadius: 10, background: pct > 70 ? 'var(--positive-soft)' : pct > 40 ? 'rgba(250,204,21,0.12)' : 'var(--negative-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <Icon size={18} style={{ color: barColor }} />
                        </div>
                        <div>
                          <div className="credit-factor-name">{key.replace(/_/g, " ")}</div>
                          <div style={{ fontSize: 12, color: barColor, fontWeight: 600, marginTop: 2 }}>{pct}%</div>
                        </div>
                      </div>
                      <div className="credit-factor-bar-wrap">
                        <div className="credit-factor-bar" style={{ width: `${pct}%`, background: barColor }} />
                      </div>
                      <div className="credit-factor-score">{factor.score} / {factor.max} pts</div>
                    </div>
                  );
                })}
              </div>

              {credit.tips.length > 0 && (
                <div className="card">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600 }}>
                    <Lightbulb size={18} style={{ color: 'var(--warning)' }} /> Tips to Improve
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {credit.tips.map((tip, i) => (
                      <div key={i} style={{ display: 'flex', gap: 12, padding: '14px 16px', background: 'rgba(250,204,21,0.12)', borderRadius: 12, borderLeft: '3px solid var(--warning)' }}>
                        <ArrowUp size={15} style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 2 }} />
                        <p style={{ fontSize: 14, margin: 0, lineHeight: 1.6, color: 'var(--text-primary)' }}>{tip}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Benchmarks tab */}
      {tab === "benchmarks" && (
        <div>
          {loading || !benchmarks ? (
            <div className="card"><div className="skeleton" style={{ height: 200, borderRadius: 12 }} /></div>
          ) : (
            <>
              <div className="card hero-card" style={{ marginBottom: 24 }}>
                <div className="hero-label"><TrendingUp size={16} /> Your Spending Rank</div>
                <div className="hero-amount">{benchmarks.overall_percentile}th</div>
                <div className="hero-change muted" style={{ color: 'var(--text-secondary)' }}>
                  percentile · Median: {money(benchmarks.benchmark_median)}
                </div>
              </div>

              <div className="card">
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, marginBottom: 24, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Users size={18} style={{ color: 'var(--primary)' }} /> Category Comparison
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                  {benchmarks.categories.map(cat => {
                    const STATUS_COLORS = {
                      low:     { bar: 'var(--positive)', badge: { bg: 'var(--positive-soft)', color: 'var(--positive)' } },
                      good:    { bar: 'var(--info)', badge: { bg: 'rgba(56,189,248,0.12)', color: 'var(--info)' } },
                      average: { bar: 'var(--warning)', badge: { bg: 'rgba(250,204,21,0.12)', color: 'var(--warning)' } },
                      high:    { bar: 'var(--negative)', badge: { bg: 'var(--negative-soft)', color: 'var(--negative)' } },
                    };
                    const sc = STATUS_COLORS[cat.status] || STATUS_COLORS.average;
                    return (
                      <div key={cat.category}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                          <div>
                            <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{cat.category}</span>
                            <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 8 }}>{money(cat.your_spend)}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{ ...sc.badge, padding: '3px 12px', borderRadius: 99, fontSize: 12, fontWeight: 700 }}>{cat.label}</span>
                            <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>P{cat.percentile}</span>
                          </div>
                        </div>
                        <div style={{ height: 8, background: 'var(--bg)', borderRadius: 99, overflow: 'hidden', position: 'relative' }}>
                          <div style={{ height: '100%', width: `${Math.min(100, cat.percentile)}%`, background: sc.bar, borderRadius: 99, transition: 'width 0.6s ease' }} />
                          <div style={{ position: 'absolute', top: -3, left: '50%', width: 2, height: 14, background: 'var(--text-muted)', borderRadius: 1, transform: 'translateX(-1px)' }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div style={{ marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', fontWeight: 500 }}>
                  Based on {benchmarks.sample_size} urban users · {benchmarks.methodology}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
