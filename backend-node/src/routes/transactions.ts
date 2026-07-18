import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { eq, and, or, lt, gte, ilike, desc, inArray } from "drizzle-orm";
import { Decimal } from "decimal.js";
import { db, schema } from "../db/client.js";
import { getUser } from "../auth.js";
import { HttpError } from "../lib/http-error.js";
import { logEvent, clientIp } from "../lib/audit.js";
import { cursorEncode, cursorDecode } from "../lib/cursor.js";
import { monthRange } from "../lib/month-range.js";
import { getBalanceAt } from "../lib/balance.js";
import { recordCorrection } from "../lib/category-corrections.js";

export const transactionRoutes = new Hono();

const transactionInSchema = z.object({
  date: z.string(),
  type: z.enum(["income", "expense"]),
  category: z.string(),
  amount: z.union([z.number(), z.string()]).transform((v) => String(v)).refine(
    (v) => new Decimal(v).gt(0),
    "amount must be > 0"
  ),
  description: z.string().min(1).max(500),
  source: z.string().default("cash"),
  source_ref: z.string().nullable().optional(),
  account_id: z.string().nullable().optional(),
  tags: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  running_balance: z.union([z.number(), z.string()]).nullable().optional().transform((v) => (v == null ? null : String(v))),
  stmt_seq: z.number().int().nullable().optional(),
});

const bulkDeleteSchema = z.object({
  transaction_ids: z.array(z.string()),
});

const categoryCorrectionSchema = z.object({
  category: z.string(),
});

transactionRoutes.get("/transactions", async (c) => {
  const user = getUser(c);
  const cursor = c.req.query("cursor");
  const limit = Math.min(200, Math.max(1, Number(c.req.query("limit") ?? 50)));
  const month = c.req.query("month");
  const category = c.req.query("category");
  const search = c.req.query("search");
  const txType = c.req.query("type");

  const conditions = [eq(schema.transactions.userId, user.id)];

  if (month) {
    const { start, end } = monthRange(month);
    conditions.push(gte(schema.transactions.date, start));
    conditions.push(lt(schema.transactions.date, end));
  }
  if (category) conditions.push(eq(schema.transactions.category, category));
  if (txType === "income" || txType === "expense") conditions.push(eq(schema.transactions.type, txType));
  if (search) conditions.push(ilike(schema.transactions.description, `%${search.toLowerCase()}%`));

  if (cursor) {
    const { date: cDate, id: cId } = cursorDecode(cursor);
    conditions.push(
      or(
        lt(schema.transactions.date, cDate),
        and(eq(schema.transactions.date, cDate), lt(schema.transactions.id, cId))
      )!
    );
  }

  const rows = await db
    .select()
    .from(schema.transactions)
    .where(and(...conditions))
    .orderBy(desc(schema.transactions.date), desc(schema.transactions.id))
    .limit(limit + 1);

  const hasMore = rows.length > limit;
  const items = rows.slice(0, limit);
  const nextCursor = hasMore && items.length ? cursorEncode(items[items.length - 1].date, items[items.length - 1].id) : null;

  return c.json({
    items: items.map(toTransactionOut),
    next_cursor: nextCursor,
    has_more: hasMore,
    total_returned: items.length,
  });
});

transactionRoutes.post("/transactions", zValidator("json", transactionInSchema), async (c) => {
  const user = getUser(c);
  const payload = c.req.valid("json");

  const [tx] = await db
    .insert(schema.transactions)
    .values({
      userId: user.id,
      date: payload.date,
      type: payload.type,
      category: payload.category,
      amount: payload.amount,
      description: payload.description,
      source: payload.source,
      sourceRef: payload.source_ref ?? null,
      accountId: payload.account_id ?? null,
      tags: payload.tags ?? null,
      notes: payload.notes ?? null,
      runningBalance: payload.running_balance ?? null,
      stmtSeq: payload.stmt_seq ?? null,
    })
    .returning();

  // Backfill running_balance so the DB is always the source of truth:
  // running_balance = (last known balance) ± this transaction's amount.
  let finalTx = tx;
  if (tx.runningBalance === null && tx.source !== "cash") {
    const priorBalance = await getBalanceAt(user.id, { excludeId: tx.id });
    if (priorBalance !== null) {
      const newBalance =
        tx.type === "income"
          ? new Decimal(priorBalance).plus(tx.amount)
          : new Decimal(priorBalance).minus(tx.amount);
      const [updated] = await db
        .update(schema.transactions)
        .set({ runningBalance: newBalance.toFixed(2) })
        .where(eq(schema.transactions.id, tx.id))
        .returning();
      finalTx = updated;
    }
  }

  return c.json(toTransactionOut(finalTx), 201);
});

transactionRoutes.put("/transactions/:id", zValidator("json", transactionInSchema), async (c) => {
  const user = getUser(c);
  const id = c.req.param("id");
  const payload = c.req.valid("json");

  const [existing] = await db.select().from(schema.transactions).where(eq(schema.transactions.id, id));
  if (!existing || existing.userId !== user.id) throw new HttpError(404, "Transaction not found");

  const [updated] = await db
    .update(schema.transactions)
    .set({
      date: payload.date,
      type: payload.type,
      category: payload.category,
      amount: payload.amount,
      description: payload.description,
      source: payload.source,
      sourceRef: payload.source_ref ?? null,
      accountId: payload.account_id ?? null,
      tags: payload.tags ?? null,
      notes: payload.notes ?? null,
      runningBalance: payload.running_balance ?? null,
      stmtSeq: payload.stmt_seq ?? null,
    })
    .where(eq(schema.transactions.id, id))
    .returning();

  await logEvent({
    userId: user.id, action: "update", resourceType: "transaction",
    resourceId: id, ipAddress: clientIp(c),
  });

  return c.json(toTransactionOut(updated));
});

transactionRoutes.delete("/transactions/:id", async (c) => {
  const user = getUser(c);
  const id = c.req.param("id");

  const [existing] = await db.select().from(schema.transactions).where(eq(schema.transactions.id, id));
  if (!existing || existing.userId !== user.id) throw new HttpError(404, "Transaction not found");

  await db.delete(schema.transactions).where(eq(schema.transactions.id, id));

  await logEvent({
    userId: user.id, action: "delete", resourceType: "transaction",
    resourceId: id, ipAddress: clientIp(c),
  });

  return c.json({ deleted: true });
});

transactionRoutes.post("/transactions/bulk-delete", zValidator("json", bulkDeleteSchema), async (c) => {
  const user = getUser(c);
  const { transaction_ids } = c.req.valid("json");
  if (transaction_ids.length === 0) return c.json({ deleted_count: 0 });

  const rows = await db
    .select({ id: schema.transactions.id })
    .from(schema.transactions)
    .where(and(inArray(schema.transactions.id, transaction_ids), eq(schema.transactions.userId, user.id)));

  if (rows.length === 0) return c.json({ deleted_count: 0 });

  const ids = rows.map((r) => r.id);
  await db.delete(schema.transactions).where(inArray(schema.transactions.id, ids));

  await logEvent({
    userId: user.id, action: "delete", resourceType: "transaction",
    details: { bulk: true, count: ids.length }, ipAddress: clientIp(c),
  });

  return c.json({ deleted_count: ids.length });
});

transactionRoutes.post("/transactions/:id/correct-category", zValidator("json", categoryCorrectionSchema), async (c) => {
  const user = getUser(c);
  const id = c.req.param("id");
  const { category } = c.req.valid("json");

  const [existing] = await db.select().from(schema.transactions).where(eq(schema.transactions.id, id));
  if (!existing || existing.userId !== user.id) throw new HttpError(404, "Transaction not found");

  const oldCategory = existing.category;
  await db
    .update(schema.transactions)
    .set({ category, confidence: 1.0 })
    .where(eq(schema.transactions.id, id));

  // Trains the categorization learning pipeline (Phase 5 wires it into
  // auto-categorize); the LLM/insights cache invalidation also lives there.
  await recordCorrection(user.id, existing.description, category);

  return c.json({ corrected: true, old_category: oldCategory, new_category: category });
});

function toTransactionOut(row: typeof schema.transactions.$inferSelect) {
  return {
    id: row.id,
    date: row.date,
    type: row.type,
    category: row.category,
    amount: row.amount,
    description: row.description,
    merchant_normalized: row.merchantNormalized,
    source: row.source,
    source_ref: row.sourceRef,
    confidence: row.confidence,
    account_id: row.accountId,
    tags: row.tags,
    notes: row.notes,
    running_balance: row.runningBalance,
    created_at: row.createdAt,
  };
}
