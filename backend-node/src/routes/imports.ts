import { Hono } from "hono";
import { z } from "zod";
import { db, schema } from "../db/client.js";
import { getUser } from "../auth.js";
import { eq, inArray } from "drizzle-orm";
import { getBalanceAt } from "../lib/balance.js";
import { parseCsv, parseExcel, parsePdf } from "../services/statements.js";
import { parseSms } from "../services/sms-parser.js";
import { parseReceiptImage } from "../services/receipt-ocr.js";
import crypto from "crypto";

export const importsRoutes = new Hono();

importsRoutes.post("/imports/statement", async (c) => {
  const user = getUser(c);
  const formData = await c.req.parseBody();
  const file = formData["file"] as File;
  
  if (!file || !file.name) {
    return c.json({ error: "No filename provided" }, 400);
  }
  
  const ext = file.name.split(".").pop()?.toLowerCase();
  if (!["csv", "pdf", "xls", "xlsx"].includes(ext || "")) {
    return c.json({ error: "Upload a CSV, Excel, or PDF statement" }, 400);
  }
  
  const MAX_MB = 10;
  if (file.size > MAX_MB * 1024 * 1024) {
    return c.json({ error: `File too large (max ${MAX_MB}MB)` }, 400);
  }
  
  const buffer = Buffer.from(await file.arrayBuffer());
  
  const [job] = await db.insert(schema.importJobs).values({
    userId: user.id,
    fileName: file.name,
    status: "processing"
  }).returning();
  
  // Process async
  setTimeout(async () => {
    try {
      let rows: any[] = [];
      if (ext === "csv") rows = parseCsv(buffer);
      else if (ext === "xls" || ext === "xlsx") rows = parseExcel(buffer);
      else rows = await parsePdf(buffer);
      
      if (rows.length > 5000) {
        await db.update(schema.importJobs)
          .set({ status: "failed", errorMessage: `Statement has ${rows.length} rows, over the 5000-row limit.` })
          .where(eq(schema.importJobs.id, job.id));
        return;
      }
      
      const prepared = rows.map((r, i) => {
        const fingerprint = crypto.createHash("sha256")
          .update(`${r.date}${r.amount}${r.description}`)
          .digest("hex");
        
        return {
          ...r,
          userId: user.id,
          sourceRef: fingerprint,
          stmtSeq: i
        };
      });
      
      if (prepared.length === 0) {
        await db.update(schema.importJobs)
          .set({ status: "failed", errorMessage: "No transactions could be extracted from this file." })
          .where(eq(schema.importJobs.id, job.id));
        return;
      }
      
      // Deduplicate
      const fingerprints = prepared.map(p => p.sourceRef);
      const existing = await db.select({ sourceRef: schema.transactions.sourceRef })
        .from(schema.transactions)
        .where(inArray(schema.transactions.sourceRef, fingerprints));
        
      const existingSet = new Set(existing.map(e => e.sourceRef));
      
      let priorBal: string | null = null;
      try {
        priorBal = await getBalanceAt(user.id, { excludeId: null });
      } catch (e) {
        console.warn("Could not get prior balance for backfill", e);
      }
      
      let savedCount = 0;
      const seen = new Set<string>();
      
      for (const p of prepared) {
        if (existingSet.has(p.sourceRef) || seen.has(p.sourceRef)) continue;
        seen.add(p.sourceRef);
        
        if (p.running_balance === null && priorBal !== null) {
           const pb = parseFloat(priorBal);
           const amt = parseFloat(p.amount);
           if (!isNaN(pb) && !isNaN(amt)) {
             p.runningBalance = (p.type === "income" ? pb + amt : pb - amt).toFixed(2);
             priorBal = p.runningBalance;
           }
        } else if (p.running_balance) {
           p.runningBalance = p.running_balance;
        }
        delete p.running_balance;
        
        await db.insert(schema.transactions).values(p);
        savedCount++;
      }
      
      await db.update(schema.importJobs)
        .set({ status: "done", rowCount: savedCount })
        .where(eq(schema.importJobs.id, job.id));
        
    } catch (e: any) {
      console.error("Import failed", e);
      await db.update(schema.importJobs)
        .set({ status: "failed", errorMessage: e.message?.substring(0, 500) || "Unknown error" })
        .where(eq(schema.importJobs.id, job.id));
    }
  }, 0);
  
  return c.json(job, 202);
});

importsRoutes.get("/imports/jobs/:id", async (c) => {
  const user = getUser(c);
  const id = c.req.param("id");
  
  const [job] = await db.select().from(schema.importJobs).where(eq(schema.importJobs.id, id));
  if (!job || job.userId !== user.id) {
    return c.json({ error: "Import job not found" }, 404);
  }
  
  return c.json(job);
});

importsRoutes.post("/imports/sms", async (c) => {
  const user = getUser(c);
  const { messages } = await c.req.json();
  if (!messages || !Array.isArray(messages)) return c.json({ error: "Invalid payload" }, 400);
  
  const saved = [];
  for (const message of messages) {
    const parsed = parseSms(message);
    if (!parsed) continue;
    
    const [duplicate] = await db.select().from(schema.transactions).where(
      eq(schema.transactions.sourceRef, parsed.source_ref)
    );
    if (duplicate) continue;
    
    const p = { ...parsed, userId: user.id, sourceRef: parsed.source_ref };
    delete p.source_ref;
    
    const [tx] = await db.insert(schema.transactions).values(p).returning();
    saved.push(tx);
  }
  
  return c.json(saved);
});

importsRoutes.post("/imports/receipt", async (c) => {
  const user = getUser(c);
  const formData = await c.req.parseBody();
  const file = formData["file"] as File;
  
  if (!file) return c.json({ error: "No image provided" }, 400);
  
  const buffer = Buffer.from(await file.arrayBuffer());
  const parsed = await parseReceiptImage(buffer);
  
  if (!parsed) return c.json({ error: "Could not extract receipt data" }, 400);
  
  return c.json(parsed);
});

