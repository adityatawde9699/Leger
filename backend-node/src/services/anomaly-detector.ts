function percentile(sortedVals: number[], pct: number): number {
  const n = sortedVals.length;
  if (n === 0) return 0;
  if (n === 1) return sortedVals[0];
  const idx = (pct / 100) * (n - 1);
  const lo = Math.floor(idx);
  const hi = lo + 1;
  if (hi >= n) return sortedVals[n - 1];
  const frac = idx - lo;
  return sortedVals[lo] * (1 - frac) + sortedVals[hi] * frac;
}

function meanStd(values: number[]): [number, number] {
  if (values.length === 0) return [0.0, 0.0];
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  if (n < 2) return [mean, 0.0];
  const variance = values.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / n;
  return [mean, Math.sqrt(variance)];
}

const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

export function detectAnomalies(transactions: any[]): any[] {
  if (!transactions || transactions.length === 0) return [];
  const expenses = transactions.filter(t => t.type === "expense");
  if (expenses.length === 0) return [];
  
  let anomalies: any[] = [];
  
  // 1. Large purchases
  const byCategory: Record<string, any[]> = {};
  for (const tx of expenses) {
    if (!byCategory[tx.category]) byCategory[tx.category] = [];
    byCategory[tx.category].push(tx);
  }
  
  for (const [cat, txns] of Object.entries(byCategory)) {
    if (txns.length < 5) continue;
    const amounts = txns.map(t => parseFloat(t.amount)).sort((a, b) => a - b);
    const q1 = percentile(amounts, 25);
    const q3 = percentile(amounts, 75);
    const iqr = q3 - q1;
    const fence = q3 + 1.5 * iqr;
    const med = percentile(amounts, 50);
    const threshold = med * 3.0;
    
    for (const tx of txns) {
      const amt = parseFloat(tx.amount);
      if (amt > fence && amt > threshold) {
        const ratio = amt / Math.max(fence, 1.0);
        let sev = "low";
        if (ratio >= 2.5) sev = "high";
        else if (ratio >= 1.5) sev = "medium";
        
        anomalies.push({
          transaction_id: tx.id,
          anomaly_type: "large_purchase",
          severity: sev,
          message: `Unusually large purchase: INR ${amt.toFixed(2)} in ${cat}`,
          expected_range: { min: q1, max: fence },
          date: tx.date,
          amount: amt,
          category: cat
        });
      }
    }
  }
  
  // 2. Velocity spikes
  const dailyTotals: Record<string, number> = {};
  const dailyTxns: Record<string, any[]> = {};
  for (const tx of expenses) {
    dailyTotals[tx.date] = (dailyTotals[tx.date] || 0) + parseFloat(tx.amount);
    if (!dailyTxns[tx.date]) dailyTxns[tx.date] = [];
    dailyTxns[tx.date].push(tx);
  }
  
  const dailyValues = Object.values(dailyTotals);
  if (dailyValues.length >= 3) {
    const [meanDaily, stdDaily] = meanStd(dailyValues);
    const spikeThreshold = meanDaily + 2.5 * stdDaily;
    
    if (stdDaily > 0) {
      for (const [day, total] of Object.entries(dailyTotals)) {
        if (total > spikeThreshold) {
          const ratio = total / Math.max(spikeThreshold, 1.0);
          let sev = "low";
          if (ratio >= 2.5) sev = "high";
          else if (ratio >= 1.5) sev = "medium";
          
          for (const tx of dailyTxns[day]) {
            anomalies.push({
              transaction_id: tx.id,
              anomaly_type: "velocity_spike",
              severity: sev,
              message: `Sudden spending spike: day total INR ${total.toFixed(2)}`,
              expected_range: { min: Math.max(0, meanDaily - stdDaily), max: spikeThreshold },
              date: tx.date,
              amount: parseFloat(tx.amount),
              category: tx.category
            });
          }
        }
      }
    }
  }
  
  // Deduplicate
  const seen: Record<string, any> = {};
  for (const a of anomalies) {
    const key = `${a.transaction_id}_${a.anomaly_type}`;
    if (!seen[key] || SEVERITY_ORDER[a.severity] < SEVERITY_ORDER[seen[key].severity]) {
      seen[key] = a;
    }
  }
  
  const deduped = Object.values(seen);
  
  // Sort
  return deduped.sort((a, b) => {
    if (SEVERITY_ORDER[a.severity] !== SEVERITY_ORDER[b.severity]) {
      return SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
    }
    return new Date(b.date).getTime() - new Date(a.date).getTime();
  });
}
