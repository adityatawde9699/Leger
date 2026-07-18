import { Decimal } from "decimal.js";

export const SYSTEM_PROMPT = `You are Ledger AI, a precision financial advisor for Indian users.

Core rules:
- GROUND every claim in the provided transaction data — never invent figures
- FORMAT: Use ₹ symbol, **bold** key numbers, bullet points for lists
- SPECIFIC: Reference actual merchants, categories, and amounts from the data
- COMPARE: When asked about trends, compare current vs previous periods from the data
- HONEST: If data is insufficient to answer, say so clearly and briefly
- CONCISE: Max 150 words unless user asks for detail. Lead with the most important insight.

Financial expertise:
- Savings advice must cite the user's actual savings rate from context
- Budget warnings must reference specific over-budget categories with exact amounts
- Recurring payment analysis must list detected subscriptions from context
- Investment advice must be general (you don't have live market data)

Output format:
- Use ₹ not INR for currency
- Bold key figures: **₹12,450**
- Use → for comparisons: "₹8,000 → ₹12,000"
- Never use placeholders or make up transactions`;

export function monthlySummary(transactions: any[]): any {
  let income = new Decimal(0);
  let expenses = new Decimal(0);
  const by_category: Record<string, Decimal> = {};
  const by_day: Record<string, { income: Decimal; expenses: Decimal }> = {};
  const by_month: Record<string, { income: Decimal; expenses: Decimal }> = {};
  
  let cash_income = new Decimal(0);
  let cash_expenses = new Decimal(0);
  const merchantTotals: Record<string, Decimal> = {};
  
  const dates: string[] = [];

  for (const tx of transactions) {
    const amount = new Decimal(tx.amount || 0);
    const day = tx.date; // assuming YYYY-MM-DD
    const month = tx.date.substring(0, 7); // YYYY-MM
    dates.push(day);
    
    if (!by_day[day]) by_day[day] = { income: new Decimal(0), expenses: new Decimal(0) };
    if (!by_month[month]) by_month[month] = { income: new Decimal(0), expenses: new Decimal(0) };

    if (tx.type === "expense") {
      expenses = expenses.plus(amount);
      by_category[tx.category] = (by_category[tx.category] || new Decimal(0)).plus(amount);
      by_day[day].expenses = by_day[day].expenses.plus(amount);
      by_month[month].expenses = by_month[month].expenses.plus(amount);
      
      if (tx.source === "cash") cash_expenses = cash_expenses.plus(amount);
      
      const merchant = tx.merchantNormalized || tx.description || "Unknown";
      merchantTotals[merchant] = (merchantTotals[merchant] || new Decimal(0)).plus(amount);
    } else {
      income = income.plus(amount);
      by_day[day].income = by_day[day].income.plus(amount);
      by_month[month].income = by_month[month].income.plus(amount);
      
      if (tx.source === "cash") cash_income = cash_income.plus(amount);
    }
  }

  dates.sort();
  const start_date = dates.length ? dates[0] : null;
  const end_date = dates.length ? dates[dates.length - 1] : null;
  const months_covered = new Set(dates.map(d => d.substring(0, 7))).size;

  const top_merchants = Object.entries(merchantTotals)
    .map(([m, a]) => ({ merchant: m, amount: a.toNumber() }))
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 8);
    
  const by_category_out = Object.fromEntries(Object.entries(by_category).map(([k, v]) => [k, v.toNumber()]));
  const by_day_out = Object.fromEntries(Object.entries(by_day).map(([k, v]) => [k, { income: v.income.toNumber(), expenses: v.expenses.toNumber() }]));
  const by_month_out = Object.fromEntries(Object.entries(by_month).map(([k, v]) => [k, { income: v.income.toNumber(), expenses: v.expenses.toNumber() }]));

  return {
    income: income.toNumber(),
    expenses: expenses.toNumber(),
    net: income.minus(expenses).toNumber(),
    opening_balance: null,
    closing_balance: null,
    cash_income: cash_income.toNumber(),
    cash_expenses: cash_expenses.toNumber(),
    cash_net: cash_income.minus(cash_expenses).toNumber(),
    by_category: by_category_out,
    by_day: by_day_out,
    by_month: by_month_out,
    top_merchants,
    period_start: start_date,
    period_end: end_date,
    months_covered,
  };
}

export function computeInsights(transactions: any[], budgets: any[]): string[] {
  const summary = monthlySummary(transactions);
  const insights: string[] = [];
  const budgetMap = Object.fromEntries(budgets.map(b => [b.category, new Decimal(b.monthlyLimit || 0)]));

  for (const [category, spentVal] of Object.entries(summary.by_category)) {
    const spent = new Decimal(spentVal as number);
    const budget = budgetMap[category];
    if (!budget || budget.isZero()) continue;
    
    const ratio = spent.dividedBy(budget);
    if (ratio.gte(1)) {
      insights.push(`\${category} is over budget: spent ₹\${spent.toNumber()} vs ₹\${budget.toNumber()} limit.`);
    } else if (ratio.gte(0.8)) {
      insights.push(`\${category} at \${Math.floor(ratio.toNumber() * 100)}% of budget: ₹\${spent.toNumber()} of ₹\${budget.toNumber()}.`);
    }
  }

  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
  const recent = transactions.filter(t => t.type === "expense" && new Date(t.date) >= oneWeekAgo);
  
  const merchantTotals: Record<string, Decimal> = {};
  for (const tx of recent) {
    const merchant = tx.merchantNormalized || tx.description || "Unknown";
    merchantTotals[merchant] = (merchantTotals[merchant] || new Decimal(0)).plus(tx.amount);
  }
  
  if (Object.keys(merchantTotals).length > 0) {
    let topMerchant = "";
    let maxAmt = new Decimal(0);
    for (const [m, amt] of Object.entries(merchantTotals)) {
      if (amt.gt(maxAmt)) {
        maxAmt = amt;
        topMerchant = m;
      }
    }
    insights.push(`Top weekly merchant: \${topMerchant.substring(0, 40)} at ₹\${maxAmt.toNumber()}.`);
  }

  const inc = new Decimal(summary.income);
  const exp = new Decimal(summary.expenses);
  if (inc.gt(0)) {
    const savingsRate = Math.floor(inc.minus(exp).dividedBy(inc).toNumber() * 100);
    if (savingsRate < 10) {
      insights.push(`Savings rate is only \${savingsRate}% — aim for at least 20%.`);
    } else if (savingsRate >= 30) {
      insights.push(`Excellent savings rate of \${savingsRate}% this period.`);
    }
  }

  return insights;
}

export function recurringPayments(transactions: any[]): any[] {
  const grouped: Record<string, any[]> = {};
  
  for (const tx of transactions) {
    if (tx.type === "expense") {
      const key = `\${(tx.description || "").toLowerCase()}|\${tx.category}`;
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(tx);
    }
  }
  
  const recurring = [];
  for (const [key, items] of Object.entries(grouped)) {
    if (items.length >= 2) {
      const [desc, cat] = key.split("|");
      const amounts = items.map(i => new Decimal(i.amount));
      const avg = amounts.reduce((a, b) => a.plus(b), new Decimal(0)).dividedBy(amounts.length).toNumber();
      
      const dates = items.map(i => new Date(i.date)).sort((a, b) => a.getTime() - b.getTime());
      
      let nextDate = null;
      if (dates.length >= 2) {
        const gapMs = dates[dates.length - 1].getTime() - dates[0].getTime();
        const avgGapDays = Math.floor(gapMs / (1000 * 60 * 60 * 24) / (dates.length - 1));
        const next = new Date(dates[dates.length - 1].getTime());
        next.setDate(next.getDate() + avgGapDays);
        nextDate = next.toISOString().split("T")[0];
      }
      
      recurring.push({
        description: desc.charAt(0).toUpperCase() + desc.slice(1),
        category: cat,
        average_amount: avg,
        count: items.length,
        last_date: dates[dates.length - 1].toISOString().split("T")[0],
        next_expected: nextDate,
      });
    }
  }
  
  return recurring.sort((a, b) => b.average_amount - a.average_amount);
}

export function buildAdvisorContext(transactions: any[], budgets: any[]): string {
  const summary = monthlySummary(transactions);
  const budgetMap = Object.fromEntries(budgets.map(b => [b.category, parseFloat(b.monthlyLimit)]));
  
  const budgetLines = [];
  const sortedCategories = Object.entries(summary.byCategory)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .slice(0, 10);
    
  for (const [cat, spent] of sortedCategories) {
    const limit = budgetMap[cat];
    if (limit) {
      const pct = Math.floor(((spent as number) / limit) * 100);
      const status = pct >= 100 ? " ⚠️ OVER" : (pct >= 80 ? " ⚡ NEAR" : "");
      budgetLines.push(`  ${cat}: ₹${(spent as number).toFixed(0)} / ₹${limit.toFixed(0)} (${pct}%)${status}`);
    } else {
      budgetLines.push(`  ${cat}: ₹${(spent as number).toFixed(0)} (no budget)`);
    }
  }

  const merchantLines = summary.topMerchants.slice(0, 5).map((m: any) => `  ${m.merchant.substring(0, 35)}: ₹${m.amount.toFixed(0)}`);
  
  const latest = [...transactions].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).slice(0, 20);
  const latestLines = latest.map(tx => `  ${tx.date} | ${tx.type} | ₹${tx.amount} | ${tx.category} | ${(tx.merchantNormalized || tx.description).substring(0, 60)}`);

  return `[Financial Snapshot]
Overall:
  Income: ₹${summary.income.toFixed(0)} | Expenses: ₹${summary.expenses.toFixed(0)} | Net: ₹${summary.net.toFixed(0)}

Top Spending (category vs budget):
${budgetLines.join("\\n") || "  No expense data."}

Top Merchants:
${merchantLines.join("\\n") || "  No data."}

Last 20 Transactions:
${latestLines.join("\\n") || "  No transactions found."}

Total transactions: ${transactions.length}`;
}
