import { Hono } from "hono";
import { getUser } from "../auth.js";
import { db, schema } from "../db/client.js";
import { eq, desc } from "drizzle-orm";
import { monthlySummary } from "../services/insights.js";
import { generateForecast, budgetBreachWarnings } from "../services/forecaster.js";
import { detectAnomalies } from "../services/anomaly-detector.js";

export const analyticsRoutes = new Hono();

analyticsRoutes.get("/analytics/dashboard", async (c) => {
  const user = getUser(c);
  
  const txs = await db.select().from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id))
    .orderBy(desc(schema.transactions.date));
    
  const budgets = await db.select().from(schema.budgets)
    .where(eq(schema.budgets.userId, user.id));
    
  const summary = monthlySummary(txs);
  const forecast = generateForecast(txs);
  const breaches = budgetBreachWarnings(txs, budgets);
  const anomalies = detectAnomalies(txs);
  
  return c.json({
    summary,
    forecast,
    budget_warnings: breaches,
    anomalies: anomalies.slice(0, 10)
  });
});

analyticsRoutes.get("/analytics/forecast", async (c) => {
  const user = getUser(c);
  
  const txs = await db.select().from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id))
    .orderBy(desc(schema.transactions.date));
    
  const forecast = generateForecast(txs);
  return c.json(forecast);
});

analyticsRoutes.get("/analytics/anomalies", async (c) => {
  const user = getUser(c);
  
  const txs = await db.select().from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id))
    .orderBy(desc(schema.transactions.date));
    
  const anomalies = detectAnomalies(txs);
  return c.json(anomalies);
});
