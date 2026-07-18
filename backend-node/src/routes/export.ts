import { Hono } from "hono";
import { getUser } from "../auth.js";
import { db, schema } from "../db/client.js";
import { eq, desc } from "drizzle-orm";
import { exportCsv, exportJson, exportTallyXml } from "../services/export.js";
import { logAudit } from "../services/audit.js";

export const exportRoutes = new Hono();

exportRoutes.get("/export", async (c) => {
  const user = getUser(c);
  const format = c.req.query("format") || "csv";
  
  const txs = await db.select().from(schema.transactions)
    .where(eq(schema.transactions.userId, user.id))
    .orderBy(desc(schema.transactions.date));
    
  logAudit("export_data", user.id, { format, count: txs.length });
  
  if (format === "csv") {
    const csv = exportCsv(txs);
    return new Response(csv, {
      headers: {
        "Content-Type": "text/csv",
        "Content-Disposition": 'attachment; filename="transactions.csv"'
      }
    });
  } else if (format === "tally") {
    const xml = exportTallyXml(txs);
    return new Response(xml, {
      headers: {
        "Content-Type": "application/xml",
        "Content-Disposition": 'attachment; filename="tally_import.xml"'
      }
    });
  } else {
    const json = exportJson(txs);
    return new Response(json, {
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": 'attachment; filename="transactions.json"'
      }
    });
  }
});
