import { db, schema } from "../db/client.js";

// Append-only audit trail. Caller's own insert/update already ran; this
// merely records the event — never updated or deleted afterward.
export async function logEvent(opts: {
  userId: string;
  action: "create" | "update" | "delete";
  resourceType: string;
  resourceId?: string | null;
  details?: unknown;
  ipAddress?: string | null;
}) {
  await db.insert(schema.auditLogs).values({
    userId: opts.userId,
    action: opts.action,
    resourceType: opts.resourceType,
    resourceId: opts.resourceId ?? null,
    details: opts.details ? JSON.stringify(opts.details) : null,
    ipAddress: opts.ipAddress ?? null,
  });
}

export function clientIp(c: { req: { header: (name: string) => string | undefined } }): string | null {
  const fwd = c.req.header("x-forwarded-for");
  return fwd ? fwd.split(",")[0].trim() : null;
}
