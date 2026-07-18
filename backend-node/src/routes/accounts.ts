import { Hono } from "hono";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";
import { eq, and, asc } from "drizzle-orm";
import { db, schema } from "../db/client.js";
import { getUser } from "../auth.js";
import { HttpError } from "../lib/http-error.js";
import { logEvent, clientIp } from "../lib/audit.js";

export const accountRoutes = new Hono();

const accountInSchema = z.object({
  name: z.string().min(1).max(128),
  account_type: z.enum(["savings", "current", "credit", "wallet", "cash"]),
  institution: z.string().nullable().optional(),
  balance: z.union([z.number(), z.string()]).default(0).transform((v) => String(v)),
  currency: z.string().default("INR"),
});

accountRoutes.get("/accounts", async (c) => {
  const user = getUser(c);
  const rows = await db
    .select()
    .from(schema.accounts)
    .where(and(eq(schema.accounts.userId, user.id), eq(schema.accounts.isActive, true)))
    .orderBy(asc(schema.accounts.name));
  return c.json(rows.map(toAccountOut));
});

accountRoutes.post("/accounts", zValidator("json", accountInSchema), async (c) => {
  const user = getUser(c);
  const payload = c.req.valid("json");
  const [row] = await db
    .insert(schema.accounts)
    .values({
      userId: user.id,
      name: payload.name,
      accountType: payload.account_type,
      institution: payload.institution ?? null,
      balance: payload.balance,
      currency: payload.currency,
    })
    .returning();
  return c.json(toAccountOut(row), 201);
});

accountRoutes.put("/accounts/:id", zValidator("json", accountInSchema), async (c) => {
  const user = getUser(c);
  const id = c.req.param("id");
  const payload = c.req.valid("json");

  const [existing] = await db.select().from(schema.accounts).where(eq(schema.accounts.id, id));
  if (!existing || existing.userId !== user.id) throw new HttpError(404, "Account not found");

  const [updated] = await db
    .update(schema.accounts)
    .set({
      name: payload.name,
      accountType: payload.account_type,
      institution: payload.institution ?? null,
      balance: payload.balance,
      currency: payload.currency,
    })
    .where(eq(schema.accounts.id, id))
    .returning();

  await logEvent({
    userId: user.id, action: "update", resourceType: "account",
    resourceId: id, ipAddress: clientIp(c),
  });

  return c.json(toAccountOut(updated));
});

accountRoutes.delete("/accounts/:id", async (c) => {
  const user = getUser(c);
  const id = c.req.param("id");

  const [existing] = await db.select().from(schema.accounts).where(eq(schema.accounts.id, id));
  if (!existing || existing.userId !== user.id) throw new HttpError(404, "Account not found");

  await db.update(schema.accounts).set({ isActive: false }).where(eq(schema.accounts.id, id));

  await logEvent({
    userId: user.id, action: "delete", resourceType: "account",
    resourceId: id, ipAddress: clientIp(c),
  });

  return c.json({ deleted: true });
});

function toAccountOut(row: typeof schema.accounts.$inferSelect) {
  return {
    id: row.id,
    name: row.name,
    account_type: row.accountType,
    institution: row.institution,
    balance: row.balance,
    currency: row.currency,
    is_active: row.isActive,
    created_at: row.createdAt,
    updated_at: row.updatedAt,
  };
}
