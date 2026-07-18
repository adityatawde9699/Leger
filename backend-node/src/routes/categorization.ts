import { Hono } from "hono";
import { getUser } from "../auth.js";
import { categorizeSingle, categorizeBatch } from "../services/auto-categorizer.js";
import { getUserOverrides } from "../services/categorization-learner.js";

export const categorizationRoutes = new Hono();

categorizationRoutes.post("/categorize", async (c) => {
  const user = getUser(c);
  const { description, tx_type } = await c.req.json();
  
  if (!description) return c.json({ error: "Missing description" }, 400);
  
  const overrides = await getUserOverrides(user.id);
  const result = await categorizeSingle(description, tx_type || "expense", overrides);
  
  return c.json(result);
});

categorizationRoutes.post("/categorize/batch", async (c) => {
  const user = getUser(c);
  const { transactions } = await c.req.json();
  
  if (!transactions || !Array.isArray(transactions)) {
    return c.json({ error: "Missing transactions array" }, 400);
  }
  
  const overrides = await getUserOverrides(user.id);
  const results = await categorizeBatch(transactions, overrides);
  
  return c.json(results);
});
