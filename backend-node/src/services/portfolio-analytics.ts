const RISK_FREE_RATE = 0.07;
const XIRR_MAX_ITER = 1000;
const XIRR_TOL = 1e-7;
const XIRR_INITIAL_GUESS = 0.1;

function yearsHeld(purchaseDate: Date): number {
  const delta = (new Date().getTime() - purchaseDate.getTime()) / (1000 * 60 * 60 * 24);
  const years = delta / 365.25;
  return Math.max(years, 1.0 / 365.25);
}

function annualise(simpleReturn: number, years: number): number {
  const base = 1.0 + simpleReturn;
  if (base <= 0) return -1.0;
  return Math.pow(base, 1.0 / years) - 1.0;
}

function xirrNpv(rate: number, cashflows: { date: Date; amount: number }[]): number {
  if (cashflows.length === 0) return 0.0;
  const baseDate = cashflows[0].date;
  let npv = 0.0;
  for (const cf of cashflows) {
    const t = (cf.date.getTime() - baseDate.getTime()) / (1000 * 60 * 60 * 24) / 365.25;
    npv += cf.amount / Math.pow(1.0 + rate, t);
  }
  return npv;
}

function xirr(cashflows: { date: Date; amount: number }[]): number | null {
  if (cashflows.length < 2) return null;
  const hasNegative = cashflows.some(cf => cf.amount < 0);
  const hasPositive = cashflows.some(cf => cf.amount > 0);
  if (!hasNegative || !hasPositive) return null;

  let rate = XIRR_INITIAL_GUESS;
  for (let i = 0; i < XIRR_MAX_ITER; i++) {
    const npv = xirrNpv(rate, cashflows);
    const delta = 1e-6;
    const npvDelta = xirrNpv(rate + delta, cashflows);
    const derivative = (npvDelta - npv) / delta;
    if (Math.abs(derivative) < 1e-12) break;
    
    let rateNew = rate - npv / derivative;
    if (!Number.isFinite(rateNew) || rateNew <= -1.0) {
      rateNew = rate / 2.0;
    }
    if (Math.abs(rateNew - rate) < XIRR_TOL) return Number(rateNew.toFixed(6));
    rate = rateNew;
  }
  
  if (Math.abs(xirrNpv(rate, cashflows)) < 1.0) return Number(rate.toFixed(6));
  return null;
}

function meanStd(values: number[]): [number, number] {
  if (values.length === 0) return [0.0, 0.0];
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  if (n < 2) return [mean, 0.0];
  const variance = values.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / n;
  return [mean, Math.sqrt(variance)];
}

export function computePortfolioAnalytics(portfolios: any[], holdingsByPortfolio: Record<string, any[]>): any {
  const allHoldings = [];
  for (const p of portfolios) {
    if (holdingsByPortfolio[p.id]) {
      allHoldings.push(...holdingsByPortfolio[p.id]);
    }
  }

  if (allHoldings.length === 0) {
    return {
      allocation: [],
      total_value: 0.0,
      total_invested: 0.0,
      total_return_pct: 0.0,
      annualized_return_pct: 0.0,
      sharpe_ratio: null,
      xirr: null,
      max_drawdown_pct: 0.0,
      best_performer: null,
      worst_performer: null,
      by_asset_type: {},
    };
  }

  const typeValue: Record<string, number> = {};
  const typeInvested: Record<string, number> = {};
  let totalValue = 0.0, totalInvested = 0.0;
  
  const holdingReturns: number[] = [];
  const holdingAnnualised: number[] = [];
  let bestSymbol: string | null = null;
  let bestReturn = -Infinity;
  let worstSymbol: string | null = null;
  let worstReturn = Infinity;
  
  const allCashflows: { date: Date; amount: number }[] = [];

  for (const h of allHoldings) {
    const qty = parseFloat(h.quantity || "0");
    const buyPx = parseFloat(h.buyPrice || "0");
    const curPx = parseFloat(h.currentPrice || "0");
    const invested = qty * buyPx;
    const currentVal = qty * curPx;
    
    totalValue += currentVal;
    totalInvested += invested;
    typeValue[h.assetType] = (typeValue[h.assetType] || 0) + currentVal;
    typeInvested[h.assetType] = (typeInvested[h.assetType] || 0) + invested;
    
    const simpleRet = invested > 0 ? (currentVal - invested) / invested : 0.0;
    holdingReturns.push(simpleRet);
    
    if (h.purchaseDate) {
      const pDate = new Date(h.purchaseDate);
      const annRet = annualise(simpleRet, yearsHeld(pDate));
      holdingAnnualised.push(annRet);
      allCashflows.push({ date: pDate, amount: -invested });
      allCashflows.push({ date: new Date(), amount: currentVal });
    } else {
      holdingAnnualised.push(annualise(simpleRet, 1.0));
    }
    
    if (simpleRet > bestReturn) { bestReturn = simpleRet; bestSymbol = h.symbol; }
    if (simpleRet < worstReturn) { worstReturn = simpleRet; worstSymbol = h.symbol; }
  }

  const allocation = Object.keys(typeValue).sort((a, b) => typeValue[b] - typeValue[a]).map(assetType => {
    const val = typeValue[assetType];
    const pct = totalValue > 0 ? (val / totalValue) * 100 : 0.0;
    return { asset_type: assetType, value: Number(val.toFixed(2)), pct: Number(pct.toFixed(2)), invested: Number(typeInvested[assetType].toFixed(2)) };
  });

  const totalReturnPct = totalInvested > 0 ? ((totalValue - totalInvested) / totalInvested) * 100 : 0.0;
  const annualizedReturnPct = holdingAnnualised.length > 0 ? (holdingAnnualised.reduce((a, b) => a + b, 0) / holdingAnnualised.length) * 100 : 0.0;
  
  let sharpeRatio = 0.0;
  if (holdingAnnualised.length >= 2) {
    const portfolioAnnReturn = holdingAnnualised.reduce((a, b) => a + b, 0) / holdingAnnualised.length;
    const [_, stdReturns] = meanStd(holdingAnnualised);
    if (stdReturns > 0) sharpeRatio = Number(((portfolioAnnReturn - RISK_FREE_RATE) / stdReturns).toFixed(4));
  }
  
  let xirrResult = null;
  if (allCashflows.length > 0) {
    allCashflows.sort((a, b) => a.date.getTime() - b.date.getTime());
    const res = xirr(allCashflows);
    if (res !== null) xirrResult = Number((res * 100).toFixed(4));
  }
  
  let maxDrawdownPct = 0.0;
  if (holdingReturns.length > 0) {
    let peak = holdingReturns[0];
    for (let i = 1; i < holdingReturns.length; i++) {
      const r = holdingReturns[i];
      if (r > peak) peak = r;
      const drawdown = (1.0 + peak) > 0 ? ((r - peak) / (1.0 + peak)) * 100 : 0.0;
      if (drawdown < maxDrawdownPct) maxDrawdownPct = drawdown;
    }
  }

  const byAssetType: Record<string, any> = {};
  for (const assetType of Object.keys(typeValue)) {
    const val = typeValue[assetType];
    const inv = typeInvested[assetType];
    const retPct = inv > 0 ? ((val - inv) / inv) * 100 : 0.0;
    byAssetType[assetType] = { current_value: Number(val.toFixed(2)), invested: Number(inv.toFixed(2)), return_pct: Number(retPct.toFixed(2)) };
  }

  return {
    allocation,
    total_value: Number(totalValue.toFixed(2)),
    total_invested: Number(totalInvested.toFixed(2)),
    total_return_pct: Number(totalReturnPct.toFixed(2)),
    annualized_return_pct: Number(annualizedReturnPct.toFixed(2)),
    sharpe_ratio: sharpeRatio,
    xirr: xirrResult,
    max_drawdown_pct: Number(maxDrawdownPct.toFixed(2)),
    best_performer: bestSymbol ? { symbol: bestSymbol, return_pct: Number((bestReturn * 100).toFixed(2)) } : null,
    worst_performer: worstSymbol ? { symbol: worstSymbol, return_pct: Number((worstReturn * 100).toFixed(2)) } : null,
    by_asset_type: byAssetType,
  };
}
