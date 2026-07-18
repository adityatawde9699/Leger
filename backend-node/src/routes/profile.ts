import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { eq, and, sql, count } from "drizzle-orm";
import { Decimal } from "decimal.js";
import { db, schema } from "../db/client.js";
import { getUser } from "../auth.js";
import { HttpError } from "../lib/http-error.js";

export const profileRoutes = new Hono();

const profileInSchema = z.object({
  display_name: z.string().max(128).nullable().optional(),
  avatar_url: z.string().nullable().optional(),
  currency_preference: z.string().regex(/^[A-Z]{3}$/).default("INR"),
});

profileRoutes.get("/profile", async (c) => {
  const user = getUser(c);
  const [row] = await db.select().from(schema.users).where(eq(schema.users.id, user.id));
  if (!row) throw new HttpError(404, "User not found");
  return c.json(toProfileOut(row));
});

profileRoutes.put("/profile", zValidator("json", profileInSchema), async (c) => {
  const user = getUser(c);
  const payload = c.req.valid("json");

  const [existing] = await db.select().from(schema.users).where(eq(schema.users.id, user.id));
  if (!existing) throw new HttpError(404, "User not found");

  const patch: Partial<typeof schema.users.$inferInsert> = {
    currencyPreference: payload.currency_preference,
  };
  if (payload.display_name !== undefined && payload.display_name !== null) {
    patch.displayName = payload.display_name.trim() || null;
  }
  if (payload.avatar_url !== undefined && payload.avatar_url !== null) {
    patch.avatarUrl = payload.avatar_url;
  }

  const [updated] = await db
    .update(schema.users)
    .set(patch)
    .where(eq(schema.users.id, user.id))
    .returning();

  return c.json(toProfileOut(updated));
});

profileRoutes.get("/profile/stats", async (c) => {
  const user = getUser(c);

  const [{ totalTxns }] = await db
    .select({ totalTxns: count() })
    .from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id));

  const [{ totalIncome }] = await db
    .select({ totalIncome: sql<string>`coalesce(sum(${schema.transactions.amount}), 0)` })
    .from(schema.transactions)
    .where(and(eq(schema.transactions.userId, user.id), eq(schema.transactions.type, "income")));

  const [{ totalExpenses }] = await db
    .select({ totalExpenses: sql<string>`coalesce(sum(${schema.transactions.amount}), 0)` })
    .from(schema.transactions)
    .where(and(eq(schema.transactions.userId, user.id), eq(schema.transactions.type, "expense")));

  const [{ accountsCount }] = await db
    .select({ accountsCount: count() })
    .from(schema.accounts)
    .where(and(eq(schema.accounts.userId, user.id), eq(schema.accounts.isActive, true)));

  const [{ budgetsCount }] = await db
    .select({ budgetsCount: count() })
    .from(schema.budgets)
    .where(eq(schema.budgets.userId, user.id));

  const netBalance = new Decimal(totalIncome).minus(totalExpenses);

  return c.json({
    total_transactions: totalTxns,
    total_income: totalIncome,
    total_expenses: totalExpenses,
    net_balance: netBalance.toFixed(2),
    accounts_count: accountsCount,
    budgets_count: budgetsCount,
  });
});

function toProfileOut(row: typeof schema.users.$inferSelect) {
  return {
    id: row.id,
    email: row.email,
    display_name: row.displayName,
    avatar_url: row.avatarUrl,
    currency_preference: row.currencyPreference,
    created_at: row.createdAt,
  };
}
