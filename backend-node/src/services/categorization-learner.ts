import crypto from "crypto";
import { db, schema } from "../db/client.js";
import { eq, and, desc } from "drizzle-orm";

function hashDescription(description: string): string {
  const normalized = description.toLowerCase().split(/\s+/).join(" ").trim();
  return crypto.createHash("sha256").update(normalized).digest("hex");
}

export async function getUserOverrides(userId: string): Promise<Record<string, string>> {
  try {
    const rows = await db.select()
      .from(schema.categoryCorrections)
      .where(eq(schema.categoryCorrections.userId, userId))
      .orderBy(desc(schema.categoryCorrections.correctionCount));
      
    const overrides: Record<string, string> = {};
    for (const row of rows) {
      // Because we order by correctionCount desc, the first one set takes precedence
      // Actually Drizzle result is an array, we just assign it
      if (!overrides[row.descriptionHash]) {
        overrides[row.descriptionHash] = row.category;
      }
    }
    return overrides;
  } catch (e) {
    console.error("getUserOverrides error:", e);
    return {};
  }
}

export async function recordCorrection(userId: string, description: string, newCategory: string): Promise<void> {
  const descHash = hashDescription(description);
  
  try {
    const existing = await db.select()
      .from(schema.categoryCorrections)
      .where(and(
        eq(schema.categoryCorrections.userId, userId),
        eq(schema.categoryCorrections.descriptionHash, descHash)
      ))
      .limit(1);
      
    if (existing && existing.length > 0) {
      await db.update(schema.categoryCorrections)
        .set({
          category: newCategory,
          correctionCount: (existing[0].correctionCount ?? 1) + 1
        })
        .where(eq(schema.categoryCorrections.id, existing[0].id));
    } else {
      await db.insert(schema.categoryCorrections).values({
        userId,
        descriptionHash: descHash,
        category: newCategory,
        correctionCount: 1
      });
    }
  } catch (e) {
    console.error("recordCorrection error:", e);
  }
}

export function applyUserOverrides(description: string, userOverrides: Record<string, string>): string | null {
  if (!userOverrides) return null;
  const descHash = hashDescription(description);
  return userOverrides[descHash] || null;
}
