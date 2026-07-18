import { aiRouter } from "./ai-router.js";
import { monthlySummary } from "./insights.js";

const PROACTIVE_SYSTEM = `You are a financial analyst generating PROACTIVE insights for a personal finance app.
Analyze the data and generate exactly 5-7 SHORT, actionable observations.

Rules:
- Each insight: ONE sentence, max 25 words, specific numbers only from the provided data
- Types: "warning" (risk/overspend), "tip" (action to take), "positive" (celebrate), "info" (neutral fact)
- Priority 1-5: 5=critical (over budget/anomaly), 4=important, 3=notable, 2=informational, 1=minor tip
- Include "category" field: the relevant spending category, or null
- Return ONLY a JSON array:
  [{"type": "warning|tip|positive|info", "priority": 1-5, "text": "...", "category": "...|null"}]
- No explanation outside the JSON array.`;

function buildProactiveContext(transactions: any[], budgets: any[], anomalies?: any[], forecast?: any): string {
  const summary = monthlySummary(transactions);
  const budgetMap: Record<string, number> = {};
  if (budgets) {
    for (const b of budgets) budgetMap[b.category] = parseFloat(b.monthlyLimit || "0");
  }

  const today = new Date();
  const days30Ago = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
  const days60Ago = new Date(today.getTime() - 60 * 24 * 60 * 60 * 1000);

  const last30 = transactions.filter(t => new Date(t.date) >= days30Ago);
  const prev30 = transactions.filter(t => {
    const d = new Date(t.date);
    return d >= days60Ago && d < days30Ago;
  });

  const lastSpend = last30.filter(t => t.type === "expense").reduce((a, b) => a + parseFloat(b.amount || "0"), 0);
  const prevSpend = prev30.filter(t => t.type === "expense").reduce((a, b) => a + parseFloat(b.amount || "0"), 0);
  const trendPct = prevSpend > 0 ? ((lastSpend - prevSpend) / prevSpend) * 100 : 0.0;

  const lines = [
    `Period: ${summary.period_start || "n/a"} to ${summary.period_end || "n/a"}`,
    `Income: ₹${summary.income.toFixed(0)} | Expenses: ₹${summary.expenses.toFixed(0)} | Net: ₹${summary.net.toFixed(0)}`,
    `Spending trend vs prior month: ${trendPct > 0 ? "↑" : "↓"}${Math.abs(trendPct).toFixed(0)}%`
  ];

  const catLast: Record<string, number> = {};
  const catPrev: Record<string, number> = {};
  last30.filter(t => t.type === "expense").forEach(t => catLast[t.category] = (catLast[t.category] || 0) + parseFloat(t.amount || "0"));
  prev30.filter(t => t.type === "expense").forEach(t => catPrev[t.category] = (catPrev[t.category] || 0) + parseFloat(t.amount || "0"));

  const sortedCategories = Object.entries(summary.byCategory).sort((a, b) => (b[1] as number) - (a[1] as number)).slice(0, 8);
  for (const [cat, amt] of sortedCategories) {
    const limit = budgetMap[cat];
    const pctStr = limit ? ` | budget ₹${limit.toFixed(0)} (${Math.floor((amt as number) / limit * 100)}%)` : "";
    let change = "";
    if (catPrev[cat] > 0) {
      const c = ((catLast[cat] || 0) - catPrev[cat]) / catPrev[cat] * 100;
      change = ` | ${c > 0 ? "↑" : "↓"}${Math.abs(c).toFixed(0)}% vs last month`;
    }
    lines.push(`  ${cat}: ₹${(amt as number).toFixed(0)}${pctStr}${change}`);
  }

  if (anomalies && anomalies.length > 0) {
    const high = anomalies.filter(a => ["high", "medium"].includes(a.severity)).slice(0, 3);
    if (high.length > 0) {
      lines.push(`ANOMALIES detected (${high.length}):`);
      for (const a of high) {
        lines.push(`  ${a.anomaly_type}: ₹${parseFloat(a.amount).toFixed(0)} in ${a.category} — ${a.message}`);
      }
    }
  }

  if (forecast && forecast.by_category) {
    for (const [cat, proj] of Object.entries(forecast.by_category).slice(0, 4)) {
      const limit = budgetMap[cat];
      const proj30d = (proj as any).projected_30d;
      if (limit && proj30d > limit) {
        lines.push(`FORECAST: ${cat} projected to exceed budget by ₹${(proj30d - limit).toFixed(0)} this month`);
      }
    }
  }

  return lines.join("\\n");
}

function extractJsonArray(raw: string): any[] | null {
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (e) {}
  
  let match = raw.match(/\`\`\`(?:json)?\s*(\[[\s\S]+?\])\s*\`\`\`/);
  if (match) {
    try { return JSON.parse(match[1]); } catch (e) {}
  }
  
  match = raw.match(/(\[[\s\S]+\])/);
  if (match) {
    try { return JSON.parse(match[1]); } catch (e) {}
  }
  return null;
}

function ruleBasedInsights(transactions: any[], budgets: any[], anomalies?: any[]): any[] {
  const summary = monthlySummary(transactions);
  const insights = [];
  
  if (anomalies && anomalies.length > 0) {
    const high = anomalies.filter(a => a.severity === "high").slice(0, 2);
    for (const a of high) {
      insights.push({
        type: "warning",
        priority: 5,
        text: `Unusual transaction detected: ₹${parseFloat(a.amount).toFixed(0)} in ${a.category} — ${a.message.substring(0, 50)}`,
        category: a.category
      });
    }
  }
  
  const budgetMap: Record<string, number> = {};
  if (budgets) {
    for (const b of budgets) budgetMap[b.category] = parseFloat(b.monthlyLimit || "0");
  }
  
  for (const [cat, spent] of Object.entries(summary.byCategory)) {
    const limit = budgetMap[cat];
    if (!limit) continue;
    const ratio = (spent as number) / limit;
    if (ratio >= 1.0) {
      insights.push({
        type: "warning",
        priority: 5,
        text: `${cat} is ₹${((spent as number) - limit).toFixed(0)} over budget — ₹${(spent as number).toFixed(0)} vs ₹${limit.toFixed(0)} limit.`,
        category: cat
      });
    } else if (ratio >= 0.9) {
      insights.push({
        type: "warning",
        priority: 4,
        text: `${cat} at ${Math.floor(ratio * 100)}% of budget.`,
        category: cat
      });
    }
  }
  
  const income = summary.income;
  const expenses = summary.expenses;
  const savingsRate = income > 0 ? ((income - expenses) / income) * 100 : 0;
  if (savingsRate >= 30) {
    insights.push({
      type: "positive",
      priority: 3,
      text: `Savings rate of ${savingsRate.toFixed(0)}% is excellent — you're building wealth consistently.`,
      category: null
    });
  } else if (savingsRate < 5 && income > 0) {
    insights.push({
      type: "tip",
      priority: 4,
      text: `Savings rate is only ${savingsRate.toFixed(0)}% — target 20% by reducing top spending categories.`,
      category: null
    });
  }
  
  insights.sort((a, b) => b.priority - a.priority);
  return insights.slice(0, 7);
}

export async function generateProactiveInsights(transactions: any[], budgets: any[], anomalies?: any[], forecast?: any): Promise<any[]> {
  if (!transactions || transactions.length === 0) {
    return [{ type: "info", priority: 1, text: "Add transactions to get personalized insights.", category: null }];
  }
  
  const context = buildProactiveContext(transactions, budgets, anomalies, forecast);
  
  try {
    const raw = await aiRouter.generate(PROACTIVE_SYSTEM, [{ role: "user", content: context }], undefined, "insights");
    const parsed = extractJsonArray(raw);
    if (parsed && Array.isArray(parsed)) {
      const valid = parsed.map(item => ({
        type: item.type || "info",
        priority: parseInt(item.priority || "2"),
        text: String(item.text || "").substring(0, 200),
        category: item.category || null
      })).filter(item => item.text && ["warning", "tip", "positive", "info"].includes(item.type));
      
      if (valid.length > 0) {
        return valid.sort((a, b) => b.priority - a.priority).slice(0, 7);
      }
    }
  } catch (e) {
    console.warn("Proactive LLM insights failed:", e);
  }
  
  return ruleBasedInsights(transactions, budgets, anomalies);
}
