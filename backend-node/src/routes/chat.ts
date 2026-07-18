import { Hono } from "hono";
import { getUser } from "../auth.js";
import { db, schema } from "../db/client.js";
import { eq, desc, and } from "drizzle-orm";
import { aiRouter } from "../services/ai-router.js";
import { sanitizeUserInput, buildSafeMessages } from "../services/prompt-guard.js";
import { buildAdvisorContext, SYSTEM_PROMPT } from "../services/insights.js";
import crypto from "crypto";
import { streamText } from "hono/streaming";

export const chatRoutes = new Hono();

chatRoutes.post("/advisor/stream", async (c) => {
  const user = getUser(c);
  const { question, conversation_id } = await c.req.json();
  
  if (!question) return c.json({ error: "Question is required" }, 400);
  
  const safeQuestion = sanitizeUserInput(question);
  
  // Fetch user data for context
  const txs = await db.select().from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id))
    .orderBy(desc(schema.transactions.date))
    .limit(300);
    
  const budgets = await db.select().from(schema.budgets)
    .where(eq(schema.budgets.userId, user.id));
    
  const contextText = buildAdvisorContext(txs, budgets);
  
  let history: { role: string; content: string }[] = [];
  let convId = conversation_id;
  
  if (convId) {
    const conv = await db.select().from(schema.aiConversations)
      .where(and(eq(schema.aiConversations.id, convId), eq(schema.aiConversations.userId, user.id)))
      .limit(1);
      
    if (conv.length) {
      const msgs = await db.select().from(schema.aiMessages)
        .where(eq(schema.aiMessages.conversationId, convId))
        .orderBy(schema.aiMessages.createdAt);
      history = msgs.map((m) => ({ role: m.role, content: m.content }));
    } else {
      convId = null;
    }
  }
  
  if (!convId) {
    const [newConv] = await db.insert(schema.aiConversations).values({
      userId: user.id,
      title: question.substring(0, 80),
    }).returning();
    convId = newConv.id;
  }
  
  await db.insert(schema.aiMessages).values({
    conversationId: convId,
    role: "user",
    content: question, // save the original question
  });

  const messages = buildSafeMessages(SYSTEM_PROMPT, contextText, safeQuestion, history);
  
  c.header("X-Conversation-Id", convId);
  c.header("Cache-Control", "no-cache");
  
  return streamText(c, async (stream) => {
    let fullReply = "";
    try {
      const iter = aiRouter.stream(SYSTEM_PROMPT, messages, "advisor", 900);
      for await (const chunk of iter) {
        fullReply += chunk;
        await stream.write(chunk);
      }
    } catch (e: any) {
      console.error("Advisor stream failed:", e);
      await stream.write(`\n[Error: ${e.message}]`);
    } finally {
      if (fullReply) {
        await db.insert(schema.aiMessages).values({
          conversationId: convId,
          role: "assistant",
          content: fullReply,
        });
        
        await db.update(schema.aiConversations)
          .set({ updatedAt: new Date() })
          .where(eq(schema.aiConversations.id, convId));
      }
    }
  });
});

chatRoutes.get("/conversations", async (c) => {
  const user = getUser(c);
  const convs = await db.select().from(schema.aiConversations)
    .where(eq(schema.aiConversations.userId, user.id))
    .orderBy(desc(schema.aiConversations.updatedAt))
    .limit(20);
  return c.json(convs);
});

chatRoutes.get("/conversations/:id/messages", async (c) => {
  const user = getUser(c);
  const convId = c.req.param("id");
  
  const conv = await db.select().from(schema.aiConversations)
    .where(eq(schema.aiConversations.id, convId))
    .limit(1);
    
  if (!conv.length || conv[0].userId !== user.id) {
    return c.json({ error: "Conversation not found" }, 404);
  }
  
  const messages = await db.select().from(schema.aiMessages)
    .where(eq(schema.aiMessages.conversationId, convId))
    .orderBy(schema.aiMessages.createdAt); // Ascending order
    
  return c.json(messages);
});

chatRoutes.delete("/conversations/:id", async (c) => {
  const user = getUser(c);
  const convId = c.req.param("id");
  
  const conv = await db.select().from(schema.aiConversations)
    .where(eq(schema.aiConversations.id, convId))
    .limit(1);
    
  if (!conv.length || conv[0].userId !== user.id) {
    return c.json({ error: "Conversation not found" }, 404);
  }
  
  await db.delete(schema.aiConversations).where(eq(schema.aiConversations.id, convId));
  return c.json({ status: "deleted" });
});
