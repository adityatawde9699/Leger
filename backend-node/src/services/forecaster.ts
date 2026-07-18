const EWMA_ALPHA = 0.3;
const CONF_MIN = 0.30;
const CONF_MAX = 0.95;
const MIN_MONTHS = 1;
const TREND_THRESHOLD = 0.05;

function ewma(values: number[], alpha: number = EWMA_ALPHA): number {
  if (values.length === 0) return 0.0;
  let smoothed = values[0];
  for (let i = 1; i < values.length; i++) {
    smoothed = alpha * values[i] + (1 - alpha) * smoothed;
  }
  return smoothed;
}

function meanStd(values: number[]): [number, number] {
  if (values.length === 0) return [0.0, 0.0];
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  if (n < 2) return [mean, 0.0];
  const variance = values.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / n;
  return [mean, Math.sqrt(variance)];
}

function confidenceFromCv(values: number[]): number {
  if (values.length < 2) return 0.60;
  const [mean, std] = meanStd(values);
  if (mean === 0.0) return CONF_MIN;
  const cv = std / mean;
  const raw = 1.0 / (1.0 + cv);
  return Math.max(CONF_MIN, Math.min(CONF_MAX, raw));
}

function trend(monthlyValues: number[]): string {
  if (monthlyValues.length < 2) return "stable";
  const recent = monthlyValues.slice(-2);
  const prior = monthlyValues.length >= 4 ? monthlyValues.slice(-4, -2) : monthlyValues.slice(0, Math.max(1, monthlyValues.length - 2));
  
  const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
  const priorAvg = prior.length ? (prior.reduce((a, b) => a + b, 0) / prior.length) : recentAvg;
  
  if (priorAvg === 0.0) return "stable";
  
  const change = (recentAvg - priorAvg) / priorAvg;
  if (change > TREND_THRESHOLD) return "up";
  if (change < -TREND_THRESHOLD) return "down";
  return "stable";
}

export function generateForecast(transactions: any[]): any {
  if (!transactions || transactions.length === 0) {
    return {
      by_category: {},
      total_projected_30d: 0.0,
      total_projected_60d: 0.0,
      total_projected_90d: 0.0,
      generated_at: new Date().toISOString().split("T")[0]
    };
  }

  const buckets: Record<string, Record<string, number>> = {};
  for (const tx of transactions) {
    if (tx.type === "expense") {
      const monthKey = tx.date.substring(0, 7);
      if (!buckets[tx.category]) buckets[tx.category] = {};
      buckets[tx.category][monthKey] = (buckets[tx.category][monthKey] || 0) + parseFloat(tx.amount || "0");
    }
  }

  const byCategory: Record<string, any> = {};
  let total30d = 0, total60d = 0, total90d = 0;

  for (const [category, monthMap] of Object.entries(buckets)) {
    const sortedMonths = Object.keys(monthMap).sort();
    const monthlyValues = sortedMonths.map(m => monthMap[m]);
    
    if (monthlyValues.length < MIN_MONTHS) continue;
    
    const smoothed = ewma(monthlyValues);
    const proj30 = smoothed;
    const proj60 = smoothed * 2.0;
    const proj90 = smoothed * 3.0;
    const avg = monthlyValues.reduce((a, b) => a + b, 0) / monthlyValues.length;
    
    byCategory[category] = {
      projected_30d: parseFloat(proj30.toFixed(2)),
      projected_60d: parseFloat(proj60.toFixed(2)),
      projected_90d: parseFloat(proj90.toFixed(2)),
      monthly_avg: parseFloat(avg.toFixed(2)),
      confidence: parseFloat(confidenceFromCv(monthlyValues).toFixed(4)),
      trend: trend(monthlyValues)
    };
    
    total30d += proj30;
    total60d += proj60;
    total90d += proj90;
  }

  return {
    by_category: byCategory,
    total_projected_30d: parseFloat(total30d.toFixed(2)),
    total_projected_60d: parseFloat(total60d.toFixed(2)),
    total_projected_90d: parseFloat(total90d.toFixed(2)),
    generated_at: new Date().toISOString().split("T")[0]
  };
}

export function budgetBreachWarnings(transactions: any[], budgets: any[]): any[] {
  if (!budgets || budgets.length === 0) return [];
  
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const nextMonth = new Date(today.getFullYear(), today.getMonth() + 1, 1);
  const daysInMonth = Math.round((nextMonth.getTime() - monthStart.getTime()) / (1000 * 60 * 60 * 24));
  const daysElapsed = Math.round((today.getTime() - monthStart.getTime()) / (1000 * 60 * 60 * 24)) + 1;
  const daysRemaining = daysInMonth - daysElapsed;
  
  const catSpent: Record<string, number> = {};
  for (const tx of transactions) {
    if (tx.type === "expense" && new Date(tx.date) >= monthStart) {
      catSpent[tx.category] = (catSpent[tx.category] || 0) + parseFloat(tx.amount || "0");
    }
  }
  
  const warnings = [];
  
  for (const budget of budgets) {
    const limit = parseFloat(budget.monthlyLimit || "0");
    if (limit <= 0) continue;
    
    const spent = catSpent[budget.category] || 0;
    if (spent === 0) continue;
    
    const dailyRate = spent / Math.max(daysElapsed, 1);
    const projectedTotal = dailyRate * daysInMonth;
    
    if (projectedTotal <= limit) continue;
    
    const breachRatio = projectedTotal / limit;
    let severity = "low";
    if (breachRatio >= 1.5) severity = "high";
    else if (breachRatio >= 1.2) severity = "medium";
    
    warnings.push({
      category: budget.category,
      monthly_limit: limit,
      spent_so_far: spent,
      projected_total: parseFloat(projectedTotal.toFixed(2)),
      projected_breach: parseFloat((projectedTotal - limit).toFixed(2)),
      days_elapsed: daysElapsed,
      days_remaining: daysRemaining,
      severity
    });
  }
  
  const sevOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
  return warnings.sort((a, b) => sevOrder[a.severity] - sevOrder[b.severity] || b.projected_breach - a.projected_breach);
}
