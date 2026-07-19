import { Hono } from "hono";
import { getUser } from "../auth.js";
import { db, schema } from "../db/client.js";
import { eq, desc, and, gte } from "drizzle-orm";
import { monthlySummary, computeInsights, recurringPayments } from "../services/insights.js";
import { computePortfolioAnalytics } from "../services/portfolio-analytics.js";
import { computeCreditHealth } from "../services/credit-health.js";
import { generateProactiveInsights } from "../services/proactive-insights.js";
import { generateBenchmarks } from "../services/benchmarks.js";

export const summaryRoutes = new Hono();

summaryRoutes.get("/summary", async (c) => {
  const user = getUser(c);
  const range = c.req.query("range");
  
  let txsQuery = db.select().from(schema.transactions).where(eq(schema.transactions.userId, user.id));
  
  if (range && range !== "all") {
    let startD = new Date();
    if (range === "30d") startD.setDate(startD.getDate() - 30);
    else if (range === "3m") startD.setMonth(startD.getMonth() - 3);
    else if (range === "current_year") startD = new Date(startD.getFullYear(), 0, 1);
    
    txsQuery = db.select().from(schema.transactions)
      .where(and(
        eq(schema.transactions.userId, user.id),
        gte(schema.transactions.date, startD.toISOString().split("T")[0])
      ));
  }
  
  const txs = await txsQuery;
  const budgets = await db.select().from(schema.budgets).where(eq(schema.budgets.userId, user.id));
  
  const summary = monthlySummary(txs);
  
  return c.json({
    ...summary,
    insights: computeInsights(txs, budgets),
    recurring: recurringPayments(txs),
  });
});

summaryRoutes.get("/summary/portfolio", async (c) => {
  const user = getUser(c);
  
  // Note: Drizzle models for portfolio/holdings not strictly defined yet in this demo,
  // returning empty lists for now to allow the service to return default structured values.
  const analytics = computePortfolioAnalytics([], {});
  return c.json(analytics);
});

summaryRoutes.get("/summary/credit-health", async (c) => {
  const user = getUser(c);
  
  const txs = await db.select().from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id))
    .orderBy(desc(schema.transactions.date));
    
  const budgets = await db.select().from(schema.budgets)
    .where(eq(schema.budgets.userId, user.id));
    
  const accounts = await db.select().from(schema.accounts)
    .where(eq(schema.accounts.userId, user.id));
    
  const health = computeCreditHealth(txs, budgets, accounts);
  return c.json(health);
});

async function getProactiveInsights(c: any) {
  const user = getUser(c);

  let txs: any[] = [];
  let budgets: any[] = [];

  try {
    txs = await db.select().from(schema.transactions)
      .where(eq(schema.transactions.userId, user.id))
      .orderBy(desc(schema.transactions.date));
  } catch (err) {
    console.warn("Failed to load transactions for proactive insights:", err);
  }

  try {
    budgets = await db.select().from(schema.budgets)
      .where(eq(schema.budgets.userId, user.id));
  } catch (err) {
    console.warn("Failed to load budgets for proactive insights:", err);
  }

  try {
    return await generateProactiveInsights(txs, budgets, [], {});
  } catch (err) {
    console.warn("Failed to generate proactive insights:", err);
    return [];
  }
}

summaryRoutes.get("/summary/proactive", async (c) => {
  return c.json(await getProactiveInsights(c));
});

summaryRoutes.get("/insights/proactive", async (c) => {
  return c.json(await getProactiveInsights(c));
});

summaryRoutes.get("/summary/benchmarks", async (c) => {
  const user = getUser(c);
  
  const txs = await db.select().from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id))
    .orderBy(desc(schema.transactions.date));
    
  const benchmarks = generateBenchmarks(txs);
  return c.json(benchmarks);
});
