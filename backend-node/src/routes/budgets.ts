import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { eq, and, asc, gte } from "drizzle-orm";
import { Decimal } from "decimal.js";
import { db, schema } from "../db/client.js";
import { getUser } from "../auth.js";
import { logEvent, clientIp } from "../lib/audit.js";
import { historyStart } from "../lib/history-range.js";
import { EXPENSE_CATEGORIES } from "../lib/categories.js";

export const budgetRoutes = new Hono();

const budgetInSchema = z.object({
  category: z.string(),
  monthly_limit: z.union([z.number(), z.string()]).transform((v) => String(v)).refine(
    (v) => new Decimal(v).gte(0),
    "monthly_limit must be >= 0"
  ),
  strategy: z.string().default("manual"),
});

budgetRoutes.get("/budgets", async (c) => {
  const user = getUser(c);
  const rows = await db
    .select()
    .from(schema.budgets)
    .where(eq(schema.budgets.userId, user.id))
    .orderBy(asc(schema.budgets.category));
  return c.json(rows.map(toBudgetOut));
});

budgetRoutes.put("/budgets", zValidator("json", z.array(budgetInSchema)), async (c) => {
  const user = getUser(c);
  const payload = c.req.valid("json");

  const existing = await db.select().from(schema.budgets).where(eq(schema.budgets.userId, user.id));
  const byCategory = new Map(existing.map((b) => [b.category, b]));

  const saved: (typeof schema.budgets.$inferSelect)[] = [];
  for (const item of payload) {
    const current = byCategory.get(item.category);
    if (current) {
      const [updated] = await db
        .update(schema.budgets)
        .set({ monthlyLimit: item.monthly_limit, strategy: item.strategy })
        .where(eq(schema.budgets.id, current.id))
        .returning();
      saved.push(updated);
    } else {
      const [created] = await db
        .insert(schema.budgets)
        .values({
          userId: user.id,
          category: item.category,
          monthlyLimit: item.monthly_limit,
          strategy: item.strategy,
        })
        .returning();
      saved.push(created);
    }
  }

  await logEvent({
    userId: user.id, action: "update", resourceType: "budget",
    details: { categories: payload.map((i) => i.category) }, ipAddress: clientIp(c),
  });

  return c.json(saved.map(toBudgetOut));
});

budgetRoutes.get("/budgets/suggestions", async (c) => {
  const user = getUser(c);
  const range = c.req.query("range") ?? "3m";
  const start = historyStart(range === "3m" || range === "1y" || range === "all" ? range : "3m");

  const conditions = [eq(schema.transactions.userId, user.id), eq(schema.transactions.type, "expense")];
  if (start) conditions.push(gte(schema.transactions.date, start));

  const txs = await db.select().from(schema.transactions).where(and(...conditions));
  return c.json(dynamicBudgetSuggestions(txs));
});

// Port of backend/app/services/insights.py dynamic_budget_suggestions —
// suggest budgets at 90% of observed monthly average spend per category.
function dynamicBudgetSuggestions(txs: (typeof schema.transactions.$inferSelect)[]) {
  const totals = new Map<string, Decimal>();
  const months = new Set<string>();
  for (const tx of txs) {
    months.add(tx.date.slice(0, 7));
    totals.set(tx.category, (totals.get(tx.category) ?? new Decimal(0)).plus(tx.amount));
  }
  const divisor = new Decimal(Math.max(months.size, 1));

  return EXPENSE_CATEGORIES.filter((cat) => (totals.get(cat) ?? new Decimal(0)).gt(0)).map((cat) => ({
    category: cat,
    monthly_limit: totals.get(cat)!.div(divisor).times("0.9").toDecimalPlaces(2).toFixed(2),
    strategy: `dynamic_${months.size || 1}mo_90`,
  }));
}

function toBudgetOut(row: typeof schema.budgets.$inferSelect) {
  return {
    id: row.id,
    category: row.category,
    monthly_limit: row.monthlyLimit,
    strategy: row.strategy,
    updated_at: row.updatedAt,
  };
}
