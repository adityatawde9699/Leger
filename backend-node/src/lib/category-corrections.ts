import { createHash } from "node:crypto";
import { eq, and } from "drizzle-orm";
import { db, schema } from "../db/client.js";

// Port of backend/app/services/categorization_learner.py record_correction.
// SHA-256 of the normalized description keeps raw merchant names (PII) out
// of the corrections table while still giving O(1) keyed lookups.
function normalize(description: string): string {
  return description.toLowerCase().trim().split(/\s+/).join(" ");
}

function hashDescription(description: string): string {
  return createHash("sha256").update(normalize(description), "utf-8").digest("hex");
}

export async function recordCorrection(userId: string, description: string, newCategory: string) {
  const descHash = hashDescription(description);
  try {
    const [existing] = await db
      .select()
      .from(schema.categoryCorrections)
      .where(
        and(
          eq(schema.categoryCorrections.userId, userId),
          eq(schema.categoryCorrections.descriptionHash, descHash)
        )
      );

    if (existing) {
      await db
        .update(schema.categoryCorrections)
        .set({ category: newCategory, correctionCount: existing.correctionCount + 1 })
        .where(eq(schema.categoryCorrections.id, existing.id));
    } else {
      await db.insert(schema.categoryCorrections).values({
        userId,
        descriptionHash: descHash,
        category: newCategory,
        correctionCount: 1,
      });
    }
  } catch (e) {
    // Never let a learner failure interrupt the caller's main flow.
    console.error("recordCorrection failed", e);
  }
}
