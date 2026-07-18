export function computeCreditHealth(transactions: any[], budgets: any[], accounts?: any[]): any {
  const scores: Record<string, any> = {};

  const incomes = transactions.filter(t => t.type === "income").map(t => parseFloat(t.amount || "0"));
  const expenses = transactions.filter(t => t.type === "expense").map(t => parseFloat(t.amount || "0"));
  const totalIncome = incomes.reduce((a, b) => a + b, 0) || 1;
  const totalExpense = expenses.reduce((a, b) => a + b, 0);
  const savingsRate = Math.max(0, (totalIncome - totalExpense) / totalIncome);

  let savingsScore = 30;
  if (savingsRate >= 0.35) savingsScore = 180;
  else if (savingsRate >= 0.25) savingsScore = 160;
  else if (savingsRate >= 0.20) savingsScore = 135;
  else if (savingsRate >= 0.10) savingsScore = 100;
  else if (savingsRate >= 0) savingsScore = 65;
  scores.savings = { score: savingsScore, max: 180, rate: Number((savingsRate * 100).toFixed(1)) };

  let budgetScore = 90, adherenceRate = 0.5;
  if (budgets && budgets.length > 0) {
    const catSpent: Record<string, number> = {};
    for (const t of transactions) {
      if (t.type === "expense") catSpent[t.category] = (catSpent[t.category] || 0) + parseFloat(t.amount || "0");
    }
    let adherent = 0;
    for (const b of budgets) {
      if (parseFloat(b.monthlyLimit || "0") > 0 && (catSpent[b.category] || 0) <= parseFloat(b.monthlyLimit)) {
        adherent++;
      }
    }
    adherenceRate = adherent / budgets.length;
    budgetScore = Math.floor(180 * adherenceRate);
  }
  scores.budget_adherence = { score: budgetScore, max: 180, rate: Number((adherenceRate * 100).toFixed(1)) };

  const dailySpend: Record<string, number> = {};
  for (const t of transactions) {
    if (t.type === "expense") dailySpend[t.date] = (dailySpend[t.date] || 0) + parseFloat(t.amount || "0");
  }
  let consistencyScore = 70;
  const vals = Object.values(dailySpend);
  if (vals.length > 1) {
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const variance = vals.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / vals.length;
    const cv = mean > 0 ? Math.sqrt(variance) / mean : 0;
    if (cv < 0.3) consistencyScore = 135;
    else if (cv < 0.6) consistencyScore = 105;
    else if (cv < 1.0) consistencyScore = 75;
    else consistencyScore = 45;
  }
  scores.consistency = { score: consistencyScore, max: 135 };

  const categoriesUsed = new Set(transactions.filter(t => t.type === "expense").map(t => t.category));
  const catCount = categoriesUsed.size;
  let diversityScore = 15;
  if (catCount >= 8) diversityScore = 90;
  else if (catCount >= 6) diversityScore = 75;
  else if (catCount >= 4) diversityScore = 55;
  else if (catCount >= 2) diversityScore = 35;
  scores.diversity = { score: diversityScore, max: 90, categories: catCount };

  let creditScore = 60;
  if (accounts) {
    const totalBalance = accounts.filter(a => a.isActive).reduce((a, b) => a + parseFloat(b.balance || "0"), 0);
    const creditAccounts = accounts.filter(a => a.accountType === "credit");
    if (creditAccounts.length > 0) {
      const creditBalance = creditAccounts.reduce((a, b) => a + parseFloat(b.balance || "0"), 0);
      const utilization = Math.abs(creditBalance) / (Math.abs(totalBalance) + 1);
      if (utilization < 0.2) creditScore = 90;
      else if (utilization < 0.35) creditScore = 70;
      else if (utilization < 0.5) creditScore = 45;
      else creditScore = 20;
    } else creditScore = 75;
  }
  scores.credit_utilization = { score: creditScore, max: 90 };

  const monthlyIncome: Record<string, number> = {};
  for (const t of transactions) {
    if (t.type === "income") {
      const month = t.date.substring(0, 7);
      monthlyIncome[month] = (monthlyIncome[month] || 0) + parseFloat(t.amount || "0");
    }
  }
  let incomeScore = 70;
  const incVals = Object.values(monthlyIncome);
  if (incVals.length >= 2) {
    const incMean = incVals.reduce((a, b) => a + b, 0) / incVals.length;
    const incVar = incVals.reduce((a, b) => a + Math.pow(b - incMean, 2), 0) / incVals.length;
    const incCv = incMean > 0 ? Math.sqrt(incVar) / incMean : 1;
    if (incCv < 0.1) incomeScore = 135;
    else if (incCv < 0.25) incomeScore = 110;
    else if (incCv < 0.5) incomeScore = 80;
    else incomeScore = 45;
  }
  scores.income_stability = { score: incomeScore, max: 135 };

  const monthlyNet: Record<string, number> = {};
  for (const t of transactions) {
    const month = t.date.substring(0, 7);
    const amt = parseFloat(t.amount || "0");
    monthlyNet[month] = (monthlyNet[month] || 0) + (t.type === "income" ? amt : -amt);
  }
  let trendScore = 45, trend = "stable";
  const sortedMonths = Object.keys(monthlyNet).sort().map(k => monthlyNet[k]);
  if (sortedMonths.length >= 3) {
    const mid = Math.floor(sortedMonths.length / 2);
    const priorHalf = sortedMonths.slice(0, mid);
    const recentHalf = sortedMonths.slice(mid);
    const priorAvg = priorHalf.reduce((a, b) => a + b, 0) / priorHalf.length;
    const recentAvg = recentHalf.reduce((a, b) => a + b, 0) / recentHalf.length;
    if (recentAvg > priorAvg * 1.10) { trendScore = 90; trend = "improving"; }
    else if (recentAvg > priorAvg * 0.95) { trendScore = 65; trend = "stable"; }
    else { trendScore = 30; trend = "declining"; }
  }
  scores.savings_trend = { score: trendScore, max: 90, trend };

  let total = Object.values(scores).reduce((a, b) => a + b.score, 0);
  total = Math.max(300, Math.min(900, total));

  let grade, color;
  if (total >= 800) { grade = "Excellent"; color = "#16a34a"; }
  else if (total >= 700) { grade = "Very Good"; color = "#22c55e"; }
  else if (total >= 600) { grade = "Good"; color = "#2563eb"; }
  else if (total >= 500) { grade = "Fair"; color = "#f59e0b"; }
  else if (total >= 400) { grade = "Poor"; color = "#ef4444"; }
  else { grade = "Critical"; color = "#dc2626"; }

  let emergencyMonths = null;
  if (accounts) {
    const bankBalances = accounts.filter(a => a.isActive && ["savings", "current", "wallet"].includes(a.accountType))
      .reduce((a, b) => a + parseFloat(b.balance || "0"), 0);
    const monthsActive = new Set(transactions.map(t => t.date.substring(0, 7))).size || 1;
    const avgMonthlyExpense = totalExpense / monthsActive;
    emergencyMonths = avgMonthlyExpense > 0 ? bankBalances / avgMonthlyExpense : 0;
  }

  const tips = [];
  if (savingsRate < 0.20) tips.push("Save at least 20% of your income — try automating transfers on payday");
  if (!budgets || budgets.length === 0) tips.push("Set monthly budgets for your top 3 spending categories");
  if (catCount < 5) tips.push("Track more expense categories for a complete financial picture");
  if (emergencyMonths !== null && emergencyMonths < 3) tips.push(`Build an emergency fund — you have ~${emergencyMonths.toFixed(1)} months of expenses saved`);
  if (trend === "declining") tips.push("Your savings trend is declining — review last 3 months' expenses");

  return {
    score: total,
    grade,
    color,
    breakdown: scores,
    trend,
    emergency_months: emergencyMonths !== null ? Number(emergencyMonths.toFixed(1)) : null,
    tips
  };
}
